import json, sqlite3
c = sqlite3.connect('nucleus.db')
cur = c.cursor()
for nom in ('Rendicion', 'refacturable', 'Liquidaciones'):
    row = cur.execute("SELECT id, nombre FROM proyectos WHERE lower(nombre)=lower(?)", (nom,)).fetchone()
    if not row:
        print(nom, 'NO EXISTE')
        continue
    pid = row[0]
    n = cur.execute("SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=?", (pid,)).fetchone()[0]
    print(f'--- proyecto {pid} {nom}: {n} filas')
    for k, dj in cur.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id=? LIMIT 3", (pid,)):
        d = json.loads(dj)
        print('   key=', k)
        print('   cols=', list(d.keys())[:25])
    # contar cotizaciones por estado (proyecto 8)
print('=== COTIZACIONES (proyecto 8) por estado ===')
pid = cur.execute("SELECT id FROM proyectos WHERE nombre='Cotizaciones'").fetchone()[0]
from collections import Counter
cnt = Counter()
for dj, in cur.execute("SELECT data_json FROM nucleus_data WHERE proyecto_id=?", (pid,)):
    d = json.loads(dj)
    cnt[d.get('ESTADO COTIZACION') or '(vacio)'] += 1
for k, v in cnt.items():
    print(f'   {k!r}: {v}')
