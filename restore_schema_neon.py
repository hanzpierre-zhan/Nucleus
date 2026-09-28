# restore_schema_neon.py
# Restaura app_schema, column_layout, manual_columns y primary_key
# de FLM - ENTEL desde SQLite local -> Neon
import sqlite3, json
from urllib.parse import urlparse
import psycopg2

NEON_URL = 'postgresql://neondb_owner:npg_K4mS2IGveEBw@ep-old-queen-ax41x5bx-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require'

# --- Leer local SQLite ---
sq = sqlite3.connect('nucleus.db')
sq.row_factory = sqlite3.Row
sqc = sq.cursor()
sqc.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
local_pid = sqc.fetchone()['id']
sqc.execute("SELECT clave, valor FROM app_config WHERE proyecto_id=?", (local_pid,))
local_rows = sqc.fetchall()
sq.close()

local_cfg = {}
for row in local_rows:
    v = row['valor']
    if v and v.strip():
        local_cfg[row['clave']] = v

print(f"Local FLM - ENTEL (id={local_pid}):")
for k, v in local_cfg.items():
    try:
        parsed = json.loads(v)
        count = len(parsed) if isinstance(parsed, list) else parsed
        print(f"  {k}: {count}")
    except Exception:
        print(f"  {k}: (no-json) {v[:40]}")

# --- Conectar Neon ---
p = urlparse(NEON_URL)
conn = psycopg2.connect(
    host=p.hostname, port=p.port or 5432,
    dbname=p.path.lstrip('/'),
    user=p.username, password=p.password,
    sslmode='require'
)
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
neon_pid = cur.fetchone()[0]
print(f"\nNeon FLM - ENTEL id={neon_pid}")

# --- Restaurar claves importantes ---
claves = ['app_schema', 'column_layout', 'manual_columns', 'primary_key',
          'cotizacion_margen_pct', 'servicio_opciones']

print("\nRestaurando en Neon:")
for clave in claves:
    if clave not in local_cfg:
        print(f"  {clave}: no existe en local, se omite")
        continue
    cur.execute(
        """INSERT INTO app_config (proyecto_id, clave, valor)
           VALUES (%s, %s, %s)
           ON CONFLICT (proyecto_id, clave) DO UPDATE SET valor=EXCLUDED.valor""",
        (neon_pid, clave, local_cfg[clave])
    )
    try:
        parsed = json.loads(local_cfg[clave])
        count = len(parsed) if isinstance(parsed, list) else parsed
        print(f"  OK {clave}: {count} items")
    except Exception:
        print(f"  OK {clave}: {local_cfg[clave][:40]}")

conn.commit()

# --- Verificacion final Neon ---
cur.execute("SELECT clave, valor FROM app_config WHERE proyecto_id=%s", (neon_pid,))
print("\nNeon FLM - ENTEL config final:")
for row in cur.fetchall():
    v = row[1]
    try:
        parsed = json.loads(v) if v else None
        count = len(parsed) if isinstance(parsed, list) else parsed
        print(f"  {row[0]}: {count}")
    except Exception:
        print(f"  {row[0]}: {str(v)[:40]}")

cur.close()
conn.close()
print("\nListo! Haz refresh en Render para ver todas las columnas.")
