import sqlite3, json, sys
c = sqlite3.connect('nucleus.db')
pid = c.execute("select id from proyectos where nombre='Cotizaciones'").fetchone()[0]
for clave, valor in c.execute("select clave, valor from app_config where proyecto_id=? and clave in ('manual_columns','catalogo_gastos')", (pid,)):
    print('CLAVE', clave)
    try:
        data = json.loads(valor)
    except Exception:
        print(valor[:500]); continue
    if clave == 'manual_columns':
        for col in data:
            if 'CLIENTE' in str(col.get('nombre','')).upper():
                print(col)
    else:
        print(str(data)[:500])
