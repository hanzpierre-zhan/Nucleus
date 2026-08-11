import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlalchemy
from sqlalchemy import create_engine, inspect, text, MetaData
from sqlalchemy.orm import sessionmaker

PG_URL = os.environ.get('DATABASE_URL')
if not PG_URL:
    raise SystemExit('DATABASE_URL no definida')

sqlite_path = 'nucleus.db'

os.environ['DATABASE_URL'] = PG_URL
from app import db, app

with app.app_context():
    db.create_all()

pg_engine = None
with app.app_context():
    pg_engine = db.engine
sqlite_engine = create_engine(f'sqlite:///{sqlite_path}')

sqlite_meta = MetaData()
sqlite_meta.reflect(bind=sqlite_engine)

order = ['usuarios', 'proyectos', 'app_config', 'accesos_proyecto', 'filtros_maestros',
         'tablas_maestras', 'reglas_estado_manual', 'kpi_configs', 'nucleus_data',
         'nucleus_history', 'historial_cambios', 'tecnicos']

with pg_engine.begin() as conn:
    for t in reversed(order):
        conn.execute(text(f'TRUNCATE TABLE "{t}" CASCADE'))

total = 0
with sqlite_engine.begin() as sconn:
    for t in order:
        if t not in sqlite_meta.tables:
            print(f'  (no existe en SQLite: {t})')
            continue
        st = sqlite_meta.tables[t]
        pt = db.metadata.tables[t]
        rows = [dict(r) for r in sconn.execute(sqlalchemy.select(st)).mappings()]
        if rows:
            with pg_engine.begin() as conn:
                conn.execute(pt.insert(), rows)
        total += len(rows)
        print(f'{t}: {len(rows)} filas copiadas')

with pg_engine.begin() as conn:
    for t in order:
        if t not in sqlite_meta.tables:
            continue
        pk_cols = list(sqlite_meta.tables[t].primary_key.columns)
        if len(pk_cols) == 1:
            pk = pk_cols[0].name
            seq = conn.execute(text(f"SELECT pg_get_serial_sequence('{t}', '{pk}')")).scalar()
            if seq:
                conn.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(\"{pk}\") FROM \"{t}\"), 1))"))

print(f'TOTAL: {total} filas migradas a PostgreSQL')
