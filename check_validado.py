import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()

# Get Rendicion project ID
c.execute("SELECT id FROM proyectos WHERE nombre = 'Rendicion'")
p = c.fetchone()
if not p:
    print("No project found")
    exit()
proy_id = p[0]

# Count all rows and their ESTADO
c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = ?", (proy_id,))
rows = c.fetchall()

estados = {}
for key, data_json in rows:
    try:
        d = json.loads(data_json)
        est = str(d.get('ESTADO', '') or '').strip().upper() or 'PENDIENTE'
        estados[est] = estados.get(est, 0) + 1
    except:
        pass

print("Total rows:", len(rows))
print("Por ESTADO:")
for k, v in sorted(estados.items()):
    print(f"  {k}: {v}")

# Show the 2 VALIDADO rows in detail
print("\nFilas con VALIDADO:")
for key, data_json in rows:
    try:
        d = json.loads(data_json)
        if str(d.get('ESTADO', '') or '').strip().upper() == 'VALIDADO':
            print(f"  key: {key}")
            print(f"  Nombre de site: {d.get('Nombre de site', 'NO ENCONTRADO')}")
            print(f"  Técnico beneficiario: {d.get('Técnico beneficiario', 'NO ENCONTRADO')}")
            print(f"  Todas las claves: {list(d.keys())}")
            print()
    except:
        pass
