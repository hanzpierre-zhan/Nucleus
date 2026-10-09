import sqlite3
import json

conn = sqlite3.connect('c:/Mega/Proyect/Nucleus/nucleus.db')
c = conn.cursor()
c.execute("SELECT valor FROM app_config WHERE proyecto_id = 8 AND clave = 'app_schema'")
schema_json = c.fetchone()[0]

schema = json.loads(schema_json)
print(json.dumps(schema, indent=2))
