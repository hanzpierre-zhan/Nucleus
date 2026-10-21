import sqlite3, json, collections
from datetime import date
import sys
sys.path.insert(0, '.')
c = sqlite3.connect('nucleus.db')
c.row_factory = sqlite3.Row
pid = c.execute("select id from proyectos where lower(nombre)='rendicion'").fetchone()[0]
rows = [json.loads(r['data_json']) for r in c.execute('select data_json from nucleus_data where proyecto_id=?', (pid,))]
from services.dashboard_rendicion import indicadores
det = indicadores(rows, hoy=date(2026, 10, 21))['detalle']
print(collections.Counter(r['dia_pago'] for r in det if r['dia_pago']).most_common(40))
print('n dias pago', len(set(r['dia_pago'] for r in det if r['dia_pago'])))
print('mes creacion pagos', collections.Counter(r['mes'] for r in det if r['pago_registrado']))
for pres in ('GASTO COBRA','REFACTURABLE','COSTO COBRA'):
    sus=[r for r in det if r['etapa'] in ('SUSTENTO','ATENDIDO','ARCHIVADO') and r['presupuesto']==pres]
    print(pres,'sust count',len(sus),'monto',round(sum(r['monto'] for r in sus),2))
    tot=[r for r in det if r['presupuesto']==pres]
    print('  total monto', round(sum(r['monto'] for r in tot),2), 'count', len(tot))
