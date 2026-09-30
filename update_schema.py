import sqlite3
import json

db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT id FROM proyectos WHERE nombre='Rendicion'")
proy_id = c.fetchone()[0]

c.execute("SELECT valor FROM app_config WHERE clave='app_schema' AND proyecto_id=?", (proy_id,))
row = c.fetchone()
if row:
    schema = json.loads(row[0])
else:
    schema = []

new_keys = ['SUSTENTO_MARCA TEMPORAL', 'SUSTENTO_TIPO DE PROYECTO', 'SUSTENTO_DOCUMENTO', 'SUSTENTO_TIPO DE COMPROBANTE', 'SUSTENTO_NUMERO DE COMPROBANTE', 'SUSTENTO_INGRESE RUC DE PROVEEDOR', 'SUSTENTO_PRECIO TOTAL', 'SUSTENTO_ADJUNTAR COMPROBANTE', 'SUSTENTO_CARGAR EVIDENCIAS']

schema_set = set(schema)
schema_set.update(new_keys)

c.execute("UPDATE app_config SET valor=? WHERE clave='app_schema' AND proyecto_id=?", (json.dumps(list(schema_set)), proy_id))
db.commit()
print('Schema updated successfully.')
