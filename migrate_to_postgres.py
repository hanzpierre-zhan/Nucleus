# -*- coding: utf-8 -*-
"""
migrate_to_postgres.py
======================
Migra TODOS los datos del SQLite local (nucleus.db) al PostgreSQL de Render.

USO:
    python migrate_to_postgres.py "postgres://usuario:password@host/dbname"
"""

import sys, os, sqlite3, json, re
from urllib.parse import urlparse

# ── DATABASE_URL ──────────────────────────────────────────────────────────────
DB_URL_RAW = (sys.argv[1] if len(sys.argv) > 1
              else os.environ.get('DATABASE_URL', '')).strip()

if not DB_URL_RAW:
    print("ERROR: Falta DATABASE_URL.")
    print('Uso: python migrate_to_postgres.py "postgres://user:pass@host/db"')
    sys.exit(1)

_norm = DB_URL_RAW
if _norm.startswith('postgres://'):
    _norm = 'postgresql://' + _norm[len('postgres://'):]
_parsed = urlparse(_norm)

try:
    import psycopg2
except ImportError:
    os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
    import psycopg2

pg = psycopg2.connect(
    host=_parsed.hostname,
    port=_parsed.port or 5432,
    dbname=_parsed.path.lstrip('/'),
    user=_parsed.username,
    password=_parsed.password,
    sslmode='require'
)
pg.autocommit = False
cur = pg.cursor()
print("OK Conectado a PostgreSQL.")

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nucleus.db')
sq = sqlite3.connect(SQLITE_PATH)
sq.row_factory = sqlite3.Row
sqc = sq.cursor()
print(f"OK SQLite: {SQLITE_PATH}")

# ── 1. PROYECTOS ──────────────────────────────────────────────────────────────
print("\n[1/7] Proyectos...")
sqc.execute("SELECT id, nombre, descripcion, icono FROM proyectos")
proj_id_map = {}
for p in sqc.fetchall():
    cur.execute("SELECT id FROM proyectos WHERE nombre=%s", (p['nombre'],))
    ex = cur.fetchone()
    if ex:
        proj_id_map[p['id']] = ex[0]
        print(f"  ya existe: {p['nombre']}")
    else:
        cur.execute(
            "INSERT INTO proyectos (nombre,descripcion,icono) VALUES (%s,%s,%s) RETURNING id",
            (p['nombre'], p['descripcion'] or '', p['icono'] or 'fa-folder-open'))
        nid = cur.fetchone()[0]
        proj_id_map[p['id']] = nid
        print(f"  creado: {p['nombre']} -> PG id={nid}")
pg.commit()

# ── 2. NUCLEUS_DATA ───────────────────────────────────────────────────────────
print("\n[2/7] nucleus_data...")
sqc.execute("SELECT proyecto_id, key_value, data_json FROM nucleus_data")
total = 0
for r in sqc.fetchall():
    pg_pid = proj_id_map.get(r['proyecto_id'])
    if pg_pid is None: continue
    cur.execute(
        """INSERT INTO nucleus_data (proyecto_id,key_value,data_json)
           VALUES (%s,%s,%s)
           ON CONFLICT (proyecto_id,key_value) DO UPDATE SET data_json=EXCLUDED.data_json""",
        (pg_pid, r['key_value'], r['data_json']))
    total += 1
pg.commit()
print(f"  OK {total} filas")

# ── 3. APP_CONFIG ─────────────────────────────────────────────────────────────
print("\n[3/7] app_config...")
sqc.execute("SELECT proyecto_id, clave, valor FROM app_config")
total = 0
for r in sqc.fetchall():
    pg_pid = proj_id_map.get(r['proyecto_id'])
    if pg_pid is None: continue
    cur.execute(
        """INSERT INTO app_config (proyecto_id,clave,valor)
           VALUES (%s,%s,%s)
           ON CONFLICT (proyecto_id,clave) DO UPDATE SET valor=EXCLUDED.valor""",
        (pg_pid, r['clave'], r['valor']))
    total += 1
pg.commit()
print(f"  OK {total} configs")

# ── 4. FILTROS_MAESTROS ───────────────────────────────────────────────────────
print("\n[4/7] filtros_maestros...")
try:
    sqc.execute("SELECT proyecto_id, columna, valor FROM filtros_maestros")
    total = 0
    for r in sqc.fetchall():
        pg_pid = proj_id_map.get(r['proyecto_id'])
        if pg_pid is None: continue
        cur.execute(
            """INSERT INTO filtros_maestros (proyecto_id,columna,valor)
               VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            (pg_pid, r['columna'], r['valor']))
        total += 1
    pg.commit()
    print(f"  OK {total} filtros")
except Exception as e:
    pg.rollback(); print(f"  aviso: {e}")

# ── 5. TABLAS_MAESTRAS ────────────────────────────────────────────────────────
print("\n[5/7] tablas_maestras...")
try:
    sqc.execute("SELECT proyecto_id,columna_criterio,valor_criterio,nueva_columna,nuevo_valor FROM tablas_maestras")
    total = 0
    for r in sqc.fetchall():
        pg_pid = proj_id_map.get(r['proyecto_id'])
        if pg_pid is None: continue
        cur.execute(
            """INSERT INTO tablas_maestras (proyecto_id,columna_criterio,valor_criterio,nueva_columna,nuevo_valor)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (pg_pid, r['columna_criterio'], r['valor_criterio'], r['nueva_columna'], r['nuevo_valor']))
        total += 1
    pg.commit()
    print(f"  OK {total} tablas maestras")
except Exception as e:
    pg.rollback(); print(f"  aviso: {e}")

# ── 6. TECNICOS ───────────────────────────────────────────────────────────────
print("\n[6/7] tecnicos...")
try:
    sqc.execute("SELECT proyecto_id,nombre,contrata,especialidad,telefono FROM tecnicos")
    total = 0
    for r in sqc.fetchall():
        pg_pid = proj_id_map.get(r['proyecto_id'])
        if pg_pid is None: continue
        cur.execute(
            "INSERT INTO tecnicos (proyecto_id,nombre,contrata,especialidad,telefono) VALUES (%s,%s,%s,%s,%s)",
            (pg_pid, r['nombre'], r['contrata'] or '', r['especialidad'] or '', r['telefono'] or ''))
        total += 1
    pg.commit()
    print(f"  OK {total} tecnicos")
except Exception as e:
    pg.rollback(); print(f"  aviso: {e}")

# ── 7. COTIZACIONES ───────────────────────────────────────────────────────────
print("\n[7/7] cotizaciones...")
try:
    sqc.execute("""SELECT proyecto_id,key_value,numero,nota,cotizado_por,revisado_por,
                          gastos_json,mano_obra_json,fecha_generacion,bloqueada,
                          formato,site,supervisor,items_json FROM cotizaciones""")
    total = 0
    for r in sqc.fetchall():
        pg_pid = proj_id_map.get(r['proyecto_id'])
        if pg_pid is None: continue
        cur.execute(
            """INSERT INTO cotizaciones
               (proyecto_id,key_value,numero,nota,cotizado_por,revisado_por,
                gastos_json,mano_obra_json,fecha_generacion,bloqueada,formato,site,supervisor,items_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO NOTHING""",
            (pg_pid, r['key_value'], r['numero'], r['nota'] or '',
             r['cotizado_por'] or '', r['revisado_por'] or '',
             r['gastos_json'] or '[]', r['mano_obra_json'] or '[]',
             r['fecha_generacion'], bool(r['bloqueada']),
             r['formato'] or '', r['site'] or '',
             r['supervisor'] or '', r['items_json'] or '[]'))
        total += 1
    pg.commit()
    print(f"  OK {total} cotizaciones")
except Exception as e:
    pg.rollback(); print(f"  aviso: {e}")

# ── Resumen ───────────────────────────────────────────────────────────────────
print("\n" + "="*50)
print("MIGRACION COMPLETA")
print("="*50)
cur.execute("SELECT nombre,(SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=p.id) FROM proyectos p ORDER BY nombre")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} registros")

sq.close(); cur.close(); pg.close()
print("\nListo! Render ya tiene todos tus datos.")
