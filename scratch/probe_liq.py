import json
import sqlite3

con = sqlite3.connect('nucleus.db')
con.row_factory = sqlite3.Row
cur = con.cursor()
pid = cur.execute("SELECT id FROM proyectos WHERE nombre='Cotizaciones'").fetchone()
print('proyecto Cotizaciones id=', pid['id'] if pid else None)
filas = cur.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id=?", (pid['id'],)).fetchall()
print('total cotizaciones:', len(filas))
fuera = ('cancelado', 'cancelada', 'anulado', 'anulada', 'rechazado', 'rechazada')
for f in filas:
    try:
        d = json.loads(f['data_json'])
    except Exception:
        d = {}
    est = str(d.get('ESTADO COTIZACION') or '').strip().lower()
    ing = bool(d.get('_LIQUIDACION_INGRESO')) or est not in fuera
    print('  ', f['key_value'], '|', d.get('ESTADO COTIZACION'), '| ingresada=', ing)
con.close()
