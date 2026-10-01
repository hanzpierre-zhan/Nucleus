import sqlite3
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
print('Total rows:', c.fetchone()[0])
