import json
import sqlite3
from collections import Counter

con = sqlite3.connect('file:C:/Mega/Proyect/Nucleus/nucleus.db?mode=ro', uri=True)
pid = con.execute("select id from proyectos where nombre='Rendicion'").fetchone()[0]
print('proyecto Rendicion id =', pid)

claves = Counter()
estados = Counter()
muestras = []
for key, dj in con.execute('select key_value, data_json from nucleus_data where proyecto_id=?', (pid,)):
    try:
        d = json.loads(dj or '{}')
    except Exception:
        continue
    for k in d:
        claves[k] += 1
    estados[str(d.get('ESTADO') or '(vacio)')] += 1
    if len(muestras) < 4:
        muestras.append((key, d))

print('\nCLAVES (n=%d filas):' % sum(1 for _ in con.execute('select 1 from nucleus_data where proyecto_id=?', (pid,))))
for k, c in sorted(claves.items(), key=lambda x: -x[1]):
    print('  %4d  %s' % (c, k))
print('\nESTADOS:', dict(estados))
print('\nMUESTRA:')
for key, d in muestras[:2]:
    print(' ---', key)
    for k, v in sorted(d.items()):
        print('     %-34s %r' % (k, v))
