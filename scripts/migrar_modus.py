"""Importación aditiva de Modus desde su respaldo, sin arrancar la aplicación.

Personal y cuentas existentes prevalecen. Las referencias físicas y las rutas
internas de adjuntos se remapean. La procedencia permite repetir una misma carga.
Ejecutar primero contra una copia SQLite; nunca usar el unificador de ensayo
como importador de producción.
"""
import hashlib
import json
import re
from collections import Counter

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, select


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     ensure_ascii=False).encode()).hexdigest()


def remapear_adjuntos(value, proyectos):
    """Solo cambia IDs en rutas de nuestra aplicación, nunca textos libres."""
    if isinstance(value, dict):
        return {k: remapear_adjuntos(v, proyectos) for k, v in value.items()}
    if isinstance(value, list):
        return [remapear_adjuntos(v, proyectos) for v in value]
    if not isinstance(value, str):
        return value
    pattern = r'(/api/(?:evidencia/foto|cotizacion/correo)/)(\d+)(/)'
    return re.sub(pattern, lambda m: m[1] + str(proyectos[int(m[2])]) + m[3], value)


def importar(origen, destino):
    """Engines SQLAlchemy; destino se cambia en una única transacción.

    No elimina datos ni sustituye credenciales, estados o permisos existentes.
    Guarda únicamente hashes de procedencia, sin duplicar contraseñas.
    """
    sm, dm = MetaData(), MetaData()
    sm.reflect(bind=origen)
    dm.reflect(bind=destino)
    journal = Table('migracion_modus_origen', dm,
                    Column('tabla', String(100), primary_key=True),
                    Column('id_origen', String(100), primary_key=True),
                    Column('id_destino', String(100), nullable=False),
                    Column('sha256_origen', String(64), nullable=False),
                    Column('accion', String(40), nullable=False), extend_existing=True)
    journal.create(destino, checkfirst=True)
    mapas, resumen = {}, Counter()
    with origen.connect() as src, destino.begin() as dst:
        if dst.dialect.name == 'postgresql':
            # Evita dos importadores simultáneos; la aplicación sigue operativa.
            from sqlalchemy import text
            dst.execute(text('SELECT pg_advisory_xact_lock(740182026)'))
        pendientes = dict(sm.tables)
        orden = []
        while pendientes:
            listas = [n for n, t in pendientes.items()
                      if all(f.column.table.name not in pendientes for f in t.foreign_keys)
                      and not (n == 'liquidacion_numero' and 'nucleus_data' in pendientes)
                      and not (n == 'notificaciones' and 'proyectos' in pendientes)]
            if not listas:
                raise ValueError('Dependencias cíclicas')
            for n in listas:
                orden.append(pendientes.pop(n))
        personal_id = src.scalar(select(sm.tables['proyectos'].c.id).where(
            sm.tables['proyectos'].c.nombre == 'Dataper'))
        for st in orden:
            nombre = st.name
            if nombre not in dm.tables:
                raise ValueError('Tabla de destino ausente: ' + nombre)
            dt = dm.tables[nombre]
            pk = list(st.primary_key.columns)
            if len(pk) != 1:
                raise ValueError('Se requiere clave primaria simple: ' + nombre)
            pk = pk[0].name
            mapas[nombre] = {}
            for row in src.execute(select(st)).mappings():
                original = dict(row)
                old = original[pk]
                sha = digest(original)
                previa = dst.execute(select(journal).where(
                    journal.c.tabla == nombre,
                    journal.c.id_origen == str(old))).mappings().first()
                if previa:
                    if previa['sha256_origen'] != sha:
                        raise ValueError('Origen cambiado después de migrar: ' + nombre)
                    nuevo = int(previa['id_destino'])
                    if not dst.execute(select(dt).where(dt.c[pk] == nuevo)).first():
                        raise ValueError('Procedencia sin registro de destino: ' + nombre)
                    mapas[nombre][old] = nuevo
                    resumen[nombre + ':ya_migrado'] += 1
                    continue
                datos = {k: v for k, v in original.items() if k in dt.c}
                for fk in st.foreign_keys:
                    campo, padre = fk.parent.name, fk.column.table.name
                    if datos.get(campo) is not None:
                        datos[campo] = mapas[padre][datos[campo]]
                if nombre == 'liquidacion_numero':
                    datos['origen_id'] = mapas['nucleus_data'][original['origen_id']]
                if nombre == 'notificaciones' and datos.get('proyecto_id') is not None:
                    datos['proyecto_id'] = mapas['proyectos'][original['proyecto_id']]
                if nombre == 'notificaciones':
                    leidos = [v.strip() for v in str(datos.get('leida_por') or '').replace(';', ',').split(',') if v.strip()]
                    datos['leida_por'] = ','.join(str(mapas['usuarios'][int(v)]) for v in leidos)
                existente, accion = None, 'insertado'
                if nombre == 'proyectos':
                    if datos['nombre'] == 'PEXT':
                        datos['nombre'] = 'FLM - PEXT'
                    existente = dst.execute(select(dt).where(
                        dt.c.nombre == datos['nombre'])).mappings().first()
                elif nombre == 'usuarios':
                    from sqlalchemy import func
                    existente = dst.execute(select(dt).where(
                        func.lower(dt.c.username) == datos['username'].lower())).mappings().first()
                    if existente and existente['nombre'].strip().casefold() != (datos['nombre'] or '').strip().casefold():
                        raise ValueError('Cuenta homónima requiere revisión')
                elif nombre == 'nucleus_data':
                    if original['proyecto_id'] == personal_id:
                        persona = json.loads(datos['data_json'])
                        candidatos = []
                        for persona_dst in dst.execute(select(dt).where(
                                dt.c.proyecto_id == datos['proyecto_id'])).mappings():
                            actual = json.loads(persona_dst['data_json'])
                            if (str(actual.get('DOCUMENTO', '')).strip() ==
                                    str(persona.get('DOCUMENTO', '')).strip()):
                                candidatos.append(persona_dst)
                        if len(candidatos) != 1:
                            raise ValueError('Personal sin coincidencia única por documento')
                        existente = candidatos[0]
                        accion = 'personal_nucleus_conservado'
                    else:
                        existente = dst.execute(select(dt).where(
                            dt.c.proyecto_id == datos['proyecto_id'],
                            dt.c.key_value == datos['key_value'])).mappings().first()
                        datos['data_json'] = json.dumps(remapear_adjuntos(
                            json.loads(datos['data_json']), mapas['proyectos']), ensure_ascii=False)
                        if existente and json.loads(existente['data_json']) != json.loads(datos['data_json']):
                            raise ValueError('Registro operativo conflictivo; no se sobreescribe')
                elif nombre == 'app_config':
                    existente = dst.execute(select(dt).where(
                        dt.c.proyecto_id == datos['proyecto_id'],
                        dt.c.clave == datos['clave'])).mappings().first()
                    # Solo ampliar el esquema visual: no copiar secuencias,
                    # credenciales, configuración de correo o diseños anteriores.
                    if existente and datos['clave'] in ('app_schema', 'manual_columns'):
                        a, b = json.loads(existente['valor']), json.loads(datos['valor'])
                        if isinstance(a, list) and isinstance(b, list):
                            combinado = list(a)
                            for valor in b:
                                identity = lambda x: x.get('nombre') if isinstance(x, dict) else x
                                if identity(valor) not in [identity(x) for x in combinado]:
                                    combinado.append(valor)
                            if combinado != a:
                                dst.execute(dt.update().where(dt.c.id == existente['id']).values(
                                    valor=json.dumps(combinado, ensure_ascii=False)))
                                accion = 'esquema_ampliado'
                if existente is None and nombre not in ('usuarios', 'nucleus_data', 'historial_cambios', 'notificaciones'):
                    for constraint in dt.constraints:
                        from sqlalchemy import UniqueConstraint
                        if isinstance(constraint, UniqueConstraint):
                            campos = [c.name for c in constraint.columns]
                            if campos and all(datos.get(k) is not None for k in campos):
                                existente = dst.execute(select(dt).where(
                                    *(dt.c[k] == datos[k] for k in campos))).mappings().first()
                                if existente:
                                    break
                    if pk != 'id' and existente is None:
                        existente = dst.execute(select(dt).where(dt.c[pk] == datos[pk])).mappings().first()
                if existente:
                    nuevo = existente[pk]
                    if accion == 'insertado':
                        accion = 'nucleus_conservado'
                else:
                    if pk == 'id':
                        datos.pop(pk, None)
                    if nombre == 'historial_cambios':
                        datos['username'] = 'Modus: ' + datos['username']
                    result = dst.execute(dt.insert().values(**datos))
                    nuevo = result.inserted_primary_key[0]
                mapas[nombre][old] = nuevo
                dst.execute(journal.insert().values(tabla=nombre, id_origen=str(old),
                    id_destino=str(nuevo), sha256_origen=sha, accion=accion))
                resumen[nombre + ':' + accion] += 1
    return dict(resumen)
