import os
import sqlite3

for p in [r'C:\Mega\Proyect\Nucleus\nucleus.db',
          r'C:\Mega\Proyect\Nucleus\instance\nucleus.db']:
    print('=' * 70)
    print(p, 'exists=', os.path.exists(p),
          'size=%.1f MB' % (os.path.getsize(p) / 1e6) if os.path.exists(p) else '')
    try:
        c = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
        tabs = [r[0] for r in c.execute(
            "select name from sqlite_master where type='table' order by name")]
        print('  tablas:', tabs)
        if 'proyectos' in tabs:
            print('  proyectos:', [tuple(r) for r in c.execute('select id,nombre from proyectos')])
        if 'nucleus_data' in tabs:
            print('  filas nucleus_data:', c.execute('select count(*) from nucleus_data').fetchone()[0])
        c.close()
    except Exception as e:
        print('  ERROR:', e)
