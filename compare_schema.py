# compare_schema.py - Compara app_config local vs Neon y restaura si necesario
import sqlite3, json
from urllib.parse import urlparse
import psycopg2

NEON_URL = 'postgresql://neondb_owner:npg_K4mS2IGveEBw@ep-old-queen-ax41x5bx-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require'

# --- Local SQLite ---
sq = sqlite3.connect('nucleus.db')
sq.row_factory = sqlite3.Row
sqc = sq.cursor()
sqc.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
local_pid = sqc.fetchone()['id']
sqc.execute("SELECT clave, valor FROM app_config WHERE proyecto_id=?", (local_pid,))
local_cfg = {r['clave']: r['valor'] for r in sqc.fetchall()}
sq.close()

print(f"=== LOCAL SQLite FLM - ENTEL (id={local_pid}) ===")
for k, v in local_cfg.items():
    parsed = json.loads(v)
    if isinstance(parsed, list):
        print(f"  {k}: {len(parsed)} items")
    else:
        print(f"  {k}: {parsed}")

# --- Neon ---
p = urlparse(NEON_URL)
conn = psycopg2.connect(host=p.hostname, port=p.port or 5432,
    dbname=p.path.lstrip('/'), user=p.username, password=p.password, sslmode='require')
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
neon_pid = cur.fetchone()[0]
cur.execute("SELECT clave, valor FROM app_config WHERE proyecto_id=%s", (neon_pid,))
neon_cfg = {row[0]: row[1] for row in cur.fetchall()}

print(f"\n=== NEON FLM - ENTEL (id={neon_pid}) ===")
for k, v in neon_cfg.items():
    try:
        parsed = json.loads(v) if v else '(vacío)'
        if isinstance(parsed, list):
            print(f"  {k}: {len(parsed)} items")
        else:
            print(f"  {k}: {parsed}")
    except Exception:
        print(f"  {k}: {repr(v)[:60]}")

# --- Restaurar config de local a Neon ---
print("\n=== RESTAURANDO CONFIG DE LOCAL -> NEON ===")
claves_importantes = ['app_schema', 'column_layout', 'manual_columns', 'primary_key',
                      'cotizacion_margen_pct', 'servicio_opciones']
for clave in claves_importantes:
    if clave in local_cfg:
        cur.execute(
            """INSERT INTO app_config (proyecto_id, clave, valor)
               VALUES (%s, %s, %s)
               ON CONFLICT (proyecto_id, clave) DO UPDATE SET valor=EXCLUDED.valor""",
            (neon_pid, clave, local_cfg[clave])
        )
        local_parsed = json.loads(local_cfg[clave])
        items = len(local_parsed) if isinstance(local_parsed, list) else local_parsed
        print(f"  Restaurado: {clave} ({items} items)")
    else:
        print(f"  No existe en local: {clave}")

conn.commit()
print("\nOK - Config restaurada. Haz refresh en Render.")

cur.close()
conn.close()
