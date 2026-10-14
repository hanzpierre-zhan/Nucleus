import json
import sqlite3

con = sqlite3.connect('file:C:/Mega/Proyect/Nucleus/nucleus.db?mode=ro', uri=True)
con.row_factory = sqlite3.Row

mc = con.execute(
    "SELECT valor FROM app_config WHERE proyecto_id = 8 AND clave='manual_columns'"
).fetchone()
if mc:
    cols = json.loads(mc['valor'])
    print('COLUMNAS CONFIGURADAS (proyecto 8):')
    for c in cols:
        print('  -', c.get('nombre'), '(', c.get('tipo'), ')')

print()
print('CLAVES PRESENTES EN LAS FILAS (muestra de 10):')
n = 0
claves = {}
for r in con.execute("SELECT data_json FROM nucleus_data WHERE proyecto_id = 8"):
    try:
        d = json.loads(r['data_json'] or '{}')
    except Exception:
        continue
    n += 1
    for k in d:
        claves[k] = claves.get(k, 0) + 1
print('filas:', n)
for k, c in sorted(claves.items(), key=lambda x: -x[1]):
    print('  %4d  %s' % (c, k))
con.close()
