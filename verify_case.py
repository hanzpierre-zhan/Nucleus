import json, sqlite3
conn=sqlite3.connect('nucleus.db')
c=conn.cursor()
from collections import Counter
# Dataper values
c.execute("SELECT id FROM proyectos WHERE nombre='Dataper'")
pid=c.fetchone()[0]
c.execute("SELECT data_json FROM nucleus_data WHERE proyecto_id=?", (pid,))
vals=Counter()
for (dj,) in c.fetchall():
    d=json.loads(dj)
    vals[str(d.get('PROYECTO',''))]+=1
print("Dataper PROYECTO values:", dict(vals))

# Material values
c.execute("SELECT id FROM proyectos WHERE nombre='Material'")
pid2=c.fetchone()[0]
c.execute("SELECT data_json FROM nucleus_data WHERE proyecto_id=?", (pid2,))
vals2=Counter()
for (dj,) in c.fetchall():
    d=json.loads(dj)
    vals2[str(d.get('PROYECTO',''))]+=1
print("Material PROYECTO values:", dict(vals2))

# Check manual_columns in DB
c.execute("SELECT valor FROM app_config WHERE proyecto_id=? AND clave='manual_columns'", (pid,))
manual=json.loads(c.fetchone()[0])
for mc in manual:
    if mc['nombre']=='PROYECTO':
        print("Dataper PROYECTO opciones:", mc['opciones'])
c.execute("SELECT valor FROM app_config WHERE proyecto_id=? AND clave='manual_columns'", (pid2,))
manual2=json.loads(c.fetchone()[0])
for mc in manual2:
    if mc['nombre']=='PROYECTO':
        print("Material PROYECTO opciones:", mc['opciones'])
conn.close()