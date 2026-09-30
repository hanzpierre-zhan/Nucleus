import sqlite3, json

# Map broken keys to correct Spanish keys
CORRECT_KEYS = {
    'Técnico beneficiario': 'Técnico beneficiario',
    'Número CM / PM / PLM': 'Número CM / PM / PLM',
    'Monto total del depósito': 'Monto total del depósito',
    'Tipo de depósito a realizar': 'Tipo de depósito a realizar',
    'Número de celular o CCI': 'Número de celular o CCI',
    'Responsable de la validación': 'Responsable de la validación',
}

# The broken chars are U+FFFD (replacement character) used instead of proper accented chars
# Let's fix them by brute-force detecting the pattern:
BAD_TO_GOOD = {}

def fix_key(k):
    # Try replacing U+FFFD with the correct accent char based on context
    # Pattern: T?cnico -> Técnico, N?mero -> Número, dep?sito -> depósito
    # validaci?n -> validación
    import re
    k2 = k
    k2 = re.sub(r'T\ufffdcnico', 'Técnico', k2)
    k2 = re.sub(r'N\ufffdmero', 'Número', k2)
    k2 = re.sub(r'dep\ufffdsito', 'depósito', k2)
    k2 = re.sub(r'validaci\ufffdn', 'validación', k2)
    return k2

db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
rows = c.fetchall()

fixed_count = 0
for key_value, data_json in rows:
    d = json.loads(data_json)
    new_d = {}
    changed = False
    for k, v in d.items():
        new_k = fix_key(k)
        if new_k != k:
            changed = True
        new_d[new_k] = v
    if changed:
        c.execute("UPDATE nucleus_data SET data_json = ? WHERE key_value = ?", 
                  (json.dumps(new_d, ensure_ascii=False), key_value))
        print(f"Fixed: {key_value}")
        fixed_count += 1

db.commit()
print(f"Done. Fixed {fixed_count} rows.")
