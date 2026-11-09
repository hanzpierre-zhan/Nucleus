import sqlite3
c = sqlite3.connect('nucleus.db')
nombres = ['MCCLOUN', 'SERGIO', 'DAIVIS', 'EVEN', 'MARCO', 'PERCY', 'OCANA', 'SALDARRIAGA', 'GIANCARLO']
tablas = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
for tabla in tablas:
    try:
        cols = [r[1] for r in c.execute(f'pragma table_info("{tabla}")')]
    except Exception:
        continue
    for col in cols:
        try:
            for nombre in nombres:
                filas = c.execute(f'select distinct "{col}" from "{tabla}" where upper(cast("{col}" as text)) like ? limit 3', (f'%{nombre}%',)).fetchall()
                for (v,) in filas:
                    if v and len(str(v)) < 200:
                        print(tabla, col, '=>', v)
        except Exception:
            pass
