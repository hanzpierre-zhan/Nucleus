import json
import sqlite3

con = sqlite3.connect('file:C:/Mega/Proyect/Nucleus/nucleus.db?mode=ro', uri=True)
pid = con.execute("select id from proyectos where nombre='Rendicion'").fetchone()[0]
print('Rendicion id =', pid)
for clave, valor in con.execute('select clave, valor from app_config where proyecto_id=?', (pid,)):
    txt = str(valor)
    print('\n--- %s (len=%d) ---' % (clave, len(txt)))
    if clave in ('manual_columns', 'app_schema', 'column_layout', 'column_layout_vistas'):
        try:
            data = json.loads(txt)
        except Exception:
            print(txt[:400]); continue
        if isinstance(data, list):
            for c in data:
                if isinstance(c, dict):
                    print('   ', c.get('nombre'), '|', c.get('tipo'), '|', c.get('opciones'))
                else:
                    print('   ', c)
        else:
            print('   ', str(data)[:600])
    else:
        print('   ', txt[:200])
