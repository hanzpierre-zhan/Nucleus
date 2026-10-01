import sqlite3, json

db = sqlite3.connect('nucleus.db')
c = db.cursor()

c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
rows = c.fetchall()

print(f"Total rows: {len(rows)}")
print("\nESTADO per row:")
for kv, dj in rows:
    d = json.loads(dj)
    estado = d.get('ESTADO', 'MISSING!!!')
    site = d.get('Nombre de site', '?')
    print(f"  {kv} | site={site} | ESTADO={repr(estado)} | keys={list(d.keys())}")
