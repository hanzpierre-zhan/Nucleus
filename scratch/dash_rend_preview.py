import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, '.')
from services.dashboard_rendicion import indicadores

con = sqlite3.connect('file:C:/Mega/Proyect/Nucleus/nucleus.db?mode=ro', uri=True)
pid = con.execute("select id from proyectos where nombre='Rendicion'").fetchone()[0]
rows = []
for key, dj in con.execute('select key_value, data_json from nucleus_data where proyecto_id=?', (pid,)):
    d = json.loads(dj or '{}')
    d['_key'] = key
    rows.append(d)

out = indicadores(rows)
print('total:', out['total'], '| S/ total:', out['monto_total'])
print('por etapa:', dict(Counter(r['etapa'] for r in out['detalle'])))
print('por estado:', dict(Counter(r['estado'] for r in out['detalle'])))
print('abiertos con aging:', sum(1 for r in out['detalle'] if r['aging'] is not None))
print('sin monto:', sum(1 for r in out['detalle'] if not r['monto']))
