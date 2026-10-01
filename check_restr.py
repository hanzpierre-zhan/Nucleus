import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT restricciones FROM accesos_proyecto WHERE usuario_id = (SELECT id FROM usuarios WHERE username = 'hvargas') AND proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
r = c.fetchone()
print(r[0] if r else 'No restrictions')
