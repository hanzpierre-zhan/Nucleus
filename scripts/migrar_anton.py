"""Construye la migración de Anton exclusivamente sobre una copia SQLite.

La aplicación del plan en PostgreSQL es una etapa transaccional separada.
Conserva los registros existentes y archiva las versiones conflictivas.
"""
from collections import Counter
import json
import re

from sqlalchemy import Column, MetaData, String, Table, Text, UniqueConstraint, select, func

from scripts.conciliar_cotizaciones_anton import generar
from scripts.migrar_modus import digest, remapear_adjuntos
from scripts.preparar_anton import nombre_destino


def tablas_procedencia(meta):
    journal = meta.tables.get('migracion_anton_origen')
    if journal is None:
        journal = Table('migracion_anton_origen', meta,
            Column('tabla', String(100), primary_key=True),
            Column('id_origen', String(100), primary_key=True),
            Column('id_destino', String(100), nullable=False),
            Column('sha256_origen', String(64), nullable=False),
            Column('accion', String(80), nullable=False))
    versiones = meta.tables.get('migracion_anton_versiones')
    if versiones is None:
        versiones = Table('migracion_anton_versiones', meta,
            Column('tabla', String(100), primary_key=True),
            Column('id_origen', String(100), primary_key=True),
            Column('id_destino', String(100), nullable=False),
            Column('original_json', Text, nullable=False))
    return journal, versiones


def aplicar_archivos(datos, proyectos, archivos):
    if proyectos:
        datos = remapear_adjuntos(datos, proyectos)
    # Solo rutas de archivos de nuestra API. No reemplazar texto de negocio.
    for anterior, nuevo in archivos.items():
        if anterior == nuevo:
            continue
        patron = r'(/api/(?:evidencia/foto|cotizacion/correo)/\d+/)%s(?=[?"\\\s]|$)' % re.escape(anterior)
        raw = json.dumps(datos, ensure_ascii=False)
        datos = json.loads(re.sub(patron, lambda m: m[1] + nuevo, raw))
    return datos


def importar(origen, destino, archivos=None):
    if origen.dialect.name != 'sqlite' or destino.dialect.name != 'sqlite':
        raise ValueError('El constructor solo admite copias SQLite; no ejecutar contra producción')
    archivos = archivos or {}
    propuestas = generar(origen.url.database, destino.url.database, renumerar_px=True)
    cotizaciones = {r['id_anton']: r for r in propuestas['cotizaciones_modulo']}
    fisicas = {r['id_anton']: r for r in propuestas['cotizaciones_desde_wo']}
    sm, dm = MetaData(), MetaData()
    sm.reflect(origen)
    dm.reflect(destino)
    journal, versiones = tablas_procedencia(dm)
    journal.create(destino, checkfirst=True)
    versiones.create(destino, checkfirst=True)
    mapas, claves, resumen = {}, {}, Counter()
    with origen.connect() as src, destino.begin() as dst:
        nombres = {r['id']: r['nombre'] for r in src.execute(select(sm.tables['proyectos'])).mappings()}
        pendientes, orden = dict(sm.tables), []
        while pendientes:
            listas = [n for n, t in pendientes.items()
                if all(f.column.table.name not in pendientes for f in t.foreign_keys)
                and not (n == 'liquidacion_numero' and 'nucleus_data' in pendientes)
                and not (n == 'historial_cambios' and 'nucleus_data' in pendientes)
                and not (n == 'notificaciones' and 'proyectos' in pendientes)]
            if not listas:
                raise ValueError('Dependencias cíclicas')
            for n in listas:
                orden.append(pendientes.pop(n))
        for st in orden:
            nombre, dt = st.name, dm.tables[st.name]
            pk = list(st.primary_key.columns)
            if len(pk) != 1:
                raise ValueError('Clave primaria no admitida: ' + nombre)
            pk = pk[0].name
            mapas[nombre] = {}
            for row in src.execute(select(st).order_by(st.c[pk])).mappings():
                original = dict(row)
                old, sha = original[pk], digest(original)
                previa = dst.execute(select(journal).where(journal.c.tabla == nombre,
                    journal.c.id_origen == str(old))).mappings().first()
                if previa:
                    if previa['sha256_origen'] != sha:
                        raise ValueError('Origen cambiado después de migrar: ' + nombre)
                    nuevo = int(previa['id_destino'])
                    registro = dst.execute(select(dt).where(dt.c[pk] == nuevo)).mappings().first()
                    if not registro:
                        raise ValueError('Procedencia sin registro: ' + nombre)
                    mapas[nombre][old] = nuevo
                    if nombre == 'nucleus_data':
                        claves[(original['proyecto_id'], original['key_value'])] = registro['key_value']
                    resumen[nombre + ':ya_migrado'] += 1
                    continue
                datos = {k: v for k, v in original.items() if k in dt.c}
                for fk in st.foreign_keys:
                    campo = fk.parent.name
                    if datos.get(campo) is not None:
                        datos[campo] = mapas[fk.column.table.name][datos[campo]]
                existente, accion, archivar = None, 'insertado', False
                if nombre == 'proyectos':
                    datos['nombre'] = nombre_destino(datos['nombre'])
                    existente = dst.execute(select(dt).where(dt.c.nombre == datos['nombre'])).mappings().first()
                elif nombre == 'usuarios':
                    existente = dst.execute(select(dt).where(func.lower(dt.c.username) == datos['username'].lower())).mappings().first()
                    if existente and (existente['nombre'] or '').strip().casefold() != (datos['nombre'] or '').strip().casefold():
                        datos['username'] = ('anton_%s_' % old + datos['username'])[:50]
                        if dst.execute(select(dt).where(dt.c.username == datos['username'])).first():
                            raise ValueError('El alias de cuenta ya existe')
                        existente, accion = None, 'cuenta_diferenciada'
                elif nombre == 'nucleus_data':
                    modulo = nombres[original['proyecto_id']]
                    d = json.loads(original['data_json'])
                    if modulo == 'Cotizaciones':
                        propuesta = cotizaciones[old]
                        if propuesta['adaptacion']['incidencias']:
                            raise ValueError('Cotización bloqueada por validación')
                        d = aplicar_archivos(propuesta['adaptacion']['datos'], {}, archivos)
                        datos['key_value'] = propuesta['clave_destino']
                        accion = 'cotizacion_px'
                    else:
                        d = aplicar_archivos(d, mapas['proyectos'], archivos)
                    if modulo == 'Dataper':
                        d['PROYECTO'] = 'FLM - PEXT'
                        candidatos = []
                        for r in dst.execute(select(dt).where(dt.c.proyecto_id == datos['proyecto_id'])).mappings():
                            persona = json.loads(r['data_json'])
                            if str(persona.get('DOCUMENTO') or '').strip() == str(d.get('DOCUMENTO') or '').strip() and nombre_destino(str(persona.get('PROYECTO') or '')) == 'FLM - PEXT':
                                candidatos.append(r)
                        if len(candidatos) > 1:
                            raise ValueError('Personal PEXT ambiguo')
                        existente = candidatos[0] if candidatos else None
                        if not existente and dst.execute(select(dt).where(dt.c.proyecto_id == datos['proyecto_id'], dt.c.key_value == datos['key_value'])).first():
                            datos['key_value'] = str(datos['key_value'])[:70] + ' [PX-%s]' % old
                            accion = 'personal_asociacion_pext'
                    elif modulo == 'PEXT':
                        for f in fisicas.values():
                            if f['original']['key_value'] == original['key_value'] and d.get('COTIZACION_NUMERO') == f['original']['numero']:
                                d['_ANTON_COTIZACION_NUMERO_ORIGINAL'] = d['COTIZACION_NUMERO']
                                d['COTIZACION_NUMERO'] = f['adaptada']['numero']
                    elif modulo == 'Material' and d.get('PROYECTO'):
                        d['PROYECTO'] = nombre_destino(d['PROYECTO'])
                    datos['data_json'] = json.dumps(d, ensure_ascii=False)
                    if existente is None:
                        existente = dst.execute(select(dt).where(dt.c.proyecto_id == datos['proyecto_id'], dt.c.key_value == datos['key_value'])).mappings().first()
                    if existente:
                        a, b = json.loads(existente['data_json']), d
                        if modulo in ('Material', 'Dataper'):
                            a = {**a, 'PROYECTO': nombre_destino(str(a.get('PROYECTO') or ''))}
                        if a != b:
                            archivar, accion = True, 'nucleus_conservado_version_anton_archivada'
                elif nombre == 'cotizaciones':
                    datos['numero'] = fisicas[old]['adaptada']['numero']
                    datos['key_value'] = claves.get((original['proyecto_id'], original['key_value']), original['key_value'])
                elif nombre == 'historial_cambios':
                    datos['username'] = ('Anton: ' + datos['username'])[:50]
                    datos['key_value'] = claves.get((original['proyecto_id'], original['key_value']), original['key_value'])
                elif nombre == 'notificaciones':
                    if datos.get('proyecto_id') is not None:
                        datos['proyecto_id'] = mapas['proyectos'][original['proyecto_id']]
                    datos['leida_por'] = ','.join(str(mapas['usuarios'][int(v.strip())]) for v in str(datos.get('leida_por') or '').replace(';', ',').split(',') if v.strip())
                    datos['texto'] = 'Anton: ' + datos['texto']
                elif nombre == 'liquidacion_numero':
                    datos['origen_id'] = mapas['nucleus_data'][original['origen_id']]
                elif nombre == 'app_config':
                    existente = dst.execute(select(dt).where(dt.c.proyecto_id == datos['proyecto_id'], dt.c.clave == datos['clave'])).mappings().first()
                    if existente and datos['clave'] in ('app_schema', 'manual_columns'):
                        a, b = json.loads(existente['valor']), json.loads(datos['valor'])
                        if isinstance(a, list) and isinstance(b, list):
                            nuevos = list(a)
                            identidad = lambda x: x.get('nombre') if isinstance(x, dict) else x
                            for valor in b:
                                if identidad(valor) not in [identidad(x) for x in nuevos]:
                                    nuevos.append(valor)
                            if nuevos != a:
                                dst.execute(dt.update().where(dt.c.id == existente['id']).values(valor=json.dumps(nuevos, ensure_ascii=False)))
                                accion = 'esquema_ampliado'
                if existente is None and nombre not in ('usuarios', 'nucleus_data', 'cotizaciones', 'historial_cambios', 'notificaciones'):
                    for constraint in dt.constraints:
                        if isinstance(constraint, UniqueConstraint):
                            campos = [c.name for c in constraint.columns]
                            if campos and all(datos.get(k) is not None for k in campos):
                                existente = dst.execute(select(dt).where(*(dt.c[k] == datos[k] for k in campos))).mappings().first()
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
                    nuevo = dst.execute(dt.insert().values(**datos)).inserted_primary_key[0]
                if archivar:
                    dst.execute(versiones.insert().values(tabla=nombre, id_origen=str(old), id_destino=str(nuevo), original_json=json.dumps(original, default=str, ensure_ascii=False)))
                mapas[nombre][old] = nuevo
                if nombre == 'nucleus_data':
                    claves[(original['proyecto_id'], original['key_value'])] = existente['key_value'] if existente else datos['key_value']
                dst.execute(journal.insert().values(tabla=nombre, id_origen=str(old), id_destino=str(nuevo), sha256_origen=sha, accion=accion))
                resumen[nombre + ':' + accion] += 1
    return {'resumen': dict(resumen), 'numeracion': propuestas['numeracion']}
