import sqlite3
import json

db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT id FROM proyectos WHERE nombre = 'Rendicion'")
p = c.fetchone()
if p:
    c.execute("SELECT valor FROM app_config WHERE clave = 'columnas_manuales' AND proyecto_id = ?", (p[0],))
    s = c.fetchone()
    if s: print(s[0])
