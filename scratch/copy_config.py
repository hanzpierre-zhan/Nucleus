import sqlite3

conn = sqlite3.connect('c:/Mega/Proyect/Nucleus/nucleus.db')
c = conn.cursor()

c.execute("SELECT id FROM proyectos WHERE nombre = 'FLM - ENTEL'")
id_entel = c.fetchone()[0]

c.execute("SELECT id FROM proyectos WHERE nombre = 'FLM - INTEGRATEL'")
id_integratel = c.fetchone()[0]

c.execute("SELECT clave, valor FROM app_config WHERE proyecto_id = ?", (id_entel,))
configs_entel = dict(c.fetchall())

print('Schema length:', len(configs_entel.get('app_schema', '')))
print('Layout length:', len(configs_entel.get('column_layout', '')))

schema = configs_entel.get('app_schema', '[]')
layout = configs_entel.get('column_layout', '[]')
manual = configs_entel.get('manual_columns', '[]')

for key, val in [('app_schema', schema), ('column_layout', layout), ('manual_columns', manual)]:
    c.execute("SELECT id FROM app_config WHERE proyecto_id = ? AND clave = ?", (id_integratel, key))
    if c.fetchone():
        c.execute("UPDATE app_config SET valor = ? WHERE proyecto_id = ? AND clave = ?", (val, id_integratel, key))
    else:
        c.execute("INSERT INTO app_config (proyecto_id, clave, valor) VALUES (?, ?, ?)", (id_integratel, key, val))

conn.commit()
print('Copied FLM - ENTEL configuration to FLM - INTEGRATEL')
