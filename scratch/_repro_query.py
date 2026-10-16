import sqlite3

c = sqlite3.connect('file:nucleus.db?mode=ro', uri=True)
print('USERS:')
for r in c.execute('select id, username, rol from usuarios order by id'):
    print('  ', r)
print('TABLES:', [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")])
print('CONFIG KEYS:')
for r in c.execute('select distinct clave from app_config order by clave'):
    print('  ', r[0])
print('PROYECTOS:')
try:
    for r in c.execute('select id, nombre from proyectos order by id'):
        print('  ', r)
except Exception as e:
    print('  (err)', e)
