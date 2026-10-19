"""Plan revisable y carga por lotes, validada contra el destino respaldado.

El plan se genera comparando una restauración intacta y el ensayo PostgreSQL.
La carga aborta si producción cambió desde ese respaldo; no borra filas.
"""
from datetime import datetime, date
from contextlib import nullcontext
import hashlib
import json

from sqlalchemy import Date, DateTime, MetaData, select, text


def serializar(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def filas(conn, tabla):
    return [dict(r) for r in conn.execute(select(tabla).order_by(*tabla.primary_key.columns)).mappings()]


def hash_filas(rows):
    return hashlib.sha256(json.dumps(rows, default=serializar, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def construir(base, ensayo):
    mb, me = MetaData(), MetaData()
    mb.reflect(bind=base)
    me.reflect(bind=ensayo)
    plan = {'tipo': 'modus_aditivo_v1', 'tablas': {}, 'orden': []}
    with base.connect() as b, ensayo.connect() as e:
        for t in me.sorted_tables:
            nombre = t.name
            antes = filas(b, mb.tables[nombre]) if nombre in mb.tables else []
            despues = filas(e, t)
            pk = [c.name for c in t.primary_key.columns]
            if not pk:
                raise ValueError('Tabla sin clave primaria: ' + nombre)
            columnas_pk = pk
            pk = pk[0] if len(pk) == 1 else pk
            indice = {tuple(r[k] for k in columnas_pk): r for r in antes}
            nuevo = {tuple(r[k] for k in columnas_pk): r for r in despues}
            if not set(indice) <= set(nuevo):
                raise ValueError('El ensayo eliminó datos: ' + nombre)
            cambios = [r for key, r in nuevo.items() if key in indice and r != indice[key]]
            if cambios and nombre != 'app_config':
                raise ValueError('El ensayo alteró filas existentes: ' + nombre)
            if any(r['clave'] not in ('app_schema', 'manual_columns') for r in cambios):
                raise ValueError('Cambio de configuración no permitido')
            plan['tablas'][nombre] = {
                'existia': nombre in mb.tables, 'pk': pk,
                'hash_antes': hash_filas(antes), 'hash_despues': hash_filas(despues),
                'cantidad_antes': len(antes), 'cantidad_despues': len(despues),
                'insertar': [r for key, r in nuevo.items() if key not in indice],
                'actualizar': cambios}
        # Hay una referencia lógica de liquidacion_numero que carece de FK.
        orden = [t.name for t in me.sorted_tables if t.name != 'liquidacion_numero']
        if 'liquidacion_numero' in me.tables:
            orden.append('liquidacion_numero')
        plan['orden'] = orden
    return plan


def valores(fila, tabla):
    fila = dict(fila)
    for c in tabla.c:
        v = fila.get(c.name)
        if isinstance(v, str):
            if isinstance(c.type, DateTime):
                fila[c.name] = datetime.fromisoformat(v)
            elif isinstance(c.type, Date):
                fila[c.name] = date.fromisoformat(v)
    return fila


def aplicar(plan, engine, conexion=None):
    if plan['tipo'] != 'modus_aditivo_v1':
        raise ValueError('Plan desconocido')
    m = MetaData()
    m.reflect(bind=conexion if conexion is not None else engine)
    resumen = {}
    with (nullcontext(conexion) if conexion is not None else engine.begin()) as conn:
        if conn.dialect.name == 'postgresql':
            conn.execute(text("SET LOCAL lock_timeout = '15s'"))
            conn.execute(text('SELECT pg_advisory_xact_lock(740182026)'))
            nombres = ','.join(conn.dialect.identifier_preparer.quote(n)
                               for n in plan['tablas'] if n in m.tables)
            conn.exec_driver_sql('LOCK TABLE ' + nombres + ' IN SHARE ROW EXCLUSIVE MODE')
        for n, spec in plan['tablas'].items():
            actuales = filas(conn, m.tables[n]) if n in m.tables else []
            if hash_filas(actuales) != spec['hash_antes']:
                raise ValueError('Destino cambiado desde el respaldo: ' + n)
        if 'migracion_modus_origen' not in m.tables:
            from sqlalchemy import Column, String, Table
            j = Table('migracion_modus_origen', m,
                Column('tabla', String(100), primary_key=True),
                Column('id_origen', String(100), primary_key=True),
                Column('id_destino', String(100), nullable=False),
                Column('sha256_origen', String(64), nullable=False),
                Column('accion', String(40), nullable=False))
            j.create(conn)
        nuevas_anton = {'migracion_anton_origen', 'migracion_anton_versiones'} & set(plan['tablas'])
        if nuevas_anton - set(m.tables):
            from scripts.migrar_anton import tablas_procedencia
            for tabla in tablas_procedencia(m):
                tabla.create(conn, checkfirst=True)
        for n in plan['orden']:
            spec, tabla = plan['tablas'][n], m.tables[n]
            for start in range(0, len(spec['insertar']), 500):
                conn.execute(tabla.insert(), [valores(r, tabla)
                    for r in spec['insertar'][start:start + 500]])
            for row in spec['actualizar']:
                datos = valores(row, tabla)
                conn.execute(tabla.update().where(tabla.c[spec['pk']] == datos[spec['pk']]).values(**datos))
            if hash_filas(filas(conn, tabla)) != spec['hash_despues']:
                raise ValueError('Resultado distinto del ensayo: ' + n)
            if conn.dialect.name == 'postgresql' and spec['insertar'] and spec['pk'] == 'id':
                secuencia = conn.scalar(text('SELECT pg_get_serial_sequence(:tabla, :columna)'),
                    {'tabla': n, 'columna': 'id'})
                if secuencia:
                    mayor = max(r['id'] for r in filas(conn, tabla))
                    conn.execute(text('SELECT setval(CAST(:s AS regclass), '
                        'GREATEST(COALESCE(pg_sequence_last_value(CAST(:s AS regclass)),0), :maximo), true)'),
                        {'s': secuencia, 'maximo': mayor})
            resumen[n] = {'insertados': len(spec['insertar']), 'actualizados': len(spec['actualizar'])}
    return resumen
