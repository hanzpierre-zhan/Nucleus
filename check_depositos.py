import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
rows = c.fetchall()
for key, data_json in rows:
    try:
        d = json.loads(data_json)
        if str(d.get('ESTADO', '') or '').strip().upper() == 'DEPOSITADO':
            print(f"Key: {key}, Site: {d.get('Nombre de site')}, FOTOS SUSTENTO: {d.get('FOTOS SUSTENTO', 'No')}, FOTO PAGO: {d.get('FOTO PAGO', 'No')}")
            # Also print the raw keys to check for encoding issues
            if not d.get('Nombre de site'):
                print(d.keys())
    except Exception as e:
        pass
