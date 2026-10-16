import json, sqlite3
c = sqlite3.connect('nucleus.db')
cur = c.cursor()
pid = cur.execute("SELECT id FROM proyectos WHERE nombre='Cotizaciones'").fetchone()[0]
print('=== COTIZACIONES: estado | GENERADA | FECHA APROBACION ===')
for (dj,) in cur.execute('SELECT data_json FROM nucleus_data WHERE proyecto_id=?', (pid,)):
    d = json.loads(dj)
    print(repr(d.get('N° COTIZACION')), '| estado=', repr(d.get('ESTADO COTIZACION')),
          '| GENERADA=', repr(d.get('GENERADA')), '| aprob=', repr(d.get('FECHA APROBACION')),
          '| site=', str(d.get('NOMBRE SITE') or d.get('NOMBRE DE SITE') or '')[:20])
