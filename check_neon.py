# -*- coding: utf-8 -*-
"""
check_neon.py - SOLO LECTURA, no modifica nada
Verifica cuantos datos hay en Neon por proyecto.
"""
import sys, os
from urllib.parse import urlparse

URL = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get('DATABASE_URL', '')).strip()
if not URL:
    print("Uso: python check_neon.py \"postgres://...\"")
    sys.exit(1)

_u = 'postgresql://' + URL[len('postgres://'):] if URL.startswith('postgres://') else URL
p = urlparse(_u)

try:
    import psycopg2
except ImportError:
    os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
    import psycopg2

conn = psycopg2.connect(
    host=p.hostname, port=p.port or 5432,
    dbname=p.path.lstrip('/'), user=p.username,
    password=p.password, sslmode='require'
)
conn.autocommit = True
cur = conn.cursor()

print("\n========================================")
print("  VERIFICACION DE DATOS EN NEON (SOLO LECTURA)")
print("========================================\n")

# Proyectos
cur.execute("SELECT id, nombre FROM proyectos ORDER BY nombre")
proyectos = cur.fetchall()
print(f"{'PROYECTO':<25} {'REGISTROS':>10} {'APP_CONFIG':>10}")
print("-" * 50)
for pid, nombre in proyectos:
    cur.execute("SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=%s", (pid,))
    nd = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM app_config WHERE proyecto_id=%s", (pid,))
    ac = cur.fetchone()[0]
    print(f"{nombre:<25} {nd:>10} {ac:>10}")

# Total general
cur.execute("SELECT COUNT(*) FROM nucleus_data")
total_nd = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM cotizaciones")
total_cot = cur.fetchone()[0]
try:
    cur.execute("SELECT COUNT(*) FROM tecnicos")
    total_tec = cur.fetchone()[0]
except:
    total_tec = 0

print("-" * 50)
print(f"\nTotal nucleus_data : {total_nd}")
print(f"Total cotizaciones : {total_cot}")
print(f"Total tecnicos     : {total_tec}")

# Ultimos 3 registros de FLM - ENTEL como muestra
cur.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
flm = cur.fetchone()
if flm:
    cur.execute("SELECT key_value FROM nucleus_data WHERE proyecto_id=%s LIMIT 5", (flm[0],))
    keys = cur.fetchall()
    print(f"\nMuestra FLM - ENTEL (primeros 5 keys):")
    for k in keys:
        print(f"  - {k[0]}")
else:
    print("\nFLM - ENTEL: NO ENCONTRADO en Neon")

print("\n========================================")
print("  FIN - NO SE MODIFICO NADA")
print("========================================")
cur.close()
conn.close()
