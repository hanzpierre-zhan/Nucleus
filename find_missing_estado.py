import sqlite3, json

db = sqlite3.connect('nucleus.db')
c = db.cursor()

# These rows lost their ESTADO and other operational fields
# We know from previous check_validado.py output what their states were
# Let's restore them from the actual DB backup if possible,
# but since we don't have one, let's restore based on what we know

# First, let's see what ALL the missing rows look like now
c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
rows = c.fetchall()

missing_estado = []
for kv, dj in rows:
    d = json.loads(dj)
    if 'ESTADO' not in d:
        missing_estado.append((kv, d))
        
print(f"Rows missing ESTADO: {len(missing_estado)}")
for kv, d in missing_estado:
    print(f"  {kv} | site={d.get('Nombre de site', '?')}")
