# -*- coding: utf-8 -*-
import sqlite3, json
c = sqlite3.connect('nucleus.db')
cur = c.cursor()
proys = {pid: nom for pid, nom in cur.execute("SELECT id, nombre FROM proyectos")}

for pid in (9, 11, 13, 14, 15):
    print('=' * 70)
    print('PROYECTO', pid, proys.get(pid))
    for clave, valor in cur.execute("SELECT clave, valor FROM app_config WHERE proyecto_id=? AND clave IN ('app_schema','manual_columns')", (pid,)):
        try:
            v = json.loads(valor)
        except Exception:
            continue
        names = []
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and x.get('nombre'):
                    names.append(x['nombre'])
                elif isinstance(x, str):
                    names.append(x)
        print(' ', clave, '->', names)
    n = cur.execute("SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=?", (pid,)).fetchone()[0]
    print('  filas data:', n)
