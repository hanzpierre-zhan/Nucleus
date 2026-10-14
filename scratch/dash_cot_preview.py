import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, '.')
from services.dashboard_cotizaciones import indicadores

con = sqlite3.connect('file:C:/Mega/Proyect/Nucleus/nucleus.db?mode=ro', uri=True)
rows = []
for key, dj in con.execute('select key_value, data_json from nucleus_data where proyecto_id=8'):
    d = json.loads(dj)
    d['_key'] = key
    rows.append(d)

out = indicadores(rows)
print('total:', out['total'], '| S/ total:', out['monto_total'])
print('por pestania:', dict(Counter(r['pestania'] for r in out['detalle'])))
print('proveedor:', sum(r['proveedor'] for r in out['detalle']))
print('meses:', dict(Counter(r['mes'] for r in out['detalle'])))
for r in out['detalle'][:4]:
    print(' ', r['n'], '|', r['estado'], '|', r['pestania'], '| S/', r['monto'], '|', r['genero'], '|', r['cliente'], '|', r['mes'])
