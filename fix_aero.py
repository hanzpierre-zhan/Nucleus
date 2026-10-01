import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT data_json FROM nucleus_data WHERE key_value = '29/9/2026 15:41:05'")
row = c.fetchone()
if row:
    d = json.loads(row[0])
    # Fix the broken keys
    fixes = {
        'Tcnico beneficiario': 'Técnico beneficiario',
        'Nmero CM / PM / PLM': 'Número CM / PM / PLM',
        'Monto total del depsito': 'Monto total del depósito',
        'Tipo de depsito a realizar': 'Tipo de depósito a realizar',
        'Nmero de celular o CCI': 'Número de celular o CCI',
        'Responsable de la validacin': 'Responsable de la validación'
    }
    
    # We'll just copy the old bad keys to the new good keys, and delete the bad ones
    new_d = {}
    for k, v in d.items():
        fixed_k = k
        # Because the bad chars might be literally the unicode replacement char U+FFFD
        if '' in k:
            if 'T' in k and 'cnico' in k: fixed_k = 'Técnico beneficiario'
            elif 'N' in k and 'mero' in k and 'CM' in k: fixed_k = 'Número CM / PM / PLM'
            elif 'Monto' in k and 'p' in k and 'sito' in k: fixed_k = 'Monto total del depósito'
            elif 'Tipo' in k and 'p' in k and 'sito' in k: fixed_k = 'Tipo de depósito a realizar'
            elif 'N' in k and 'mero' in k and 'celular' in k: fixed_k = 'Número de celular o CCI'
            elif 'Responsable' in k and 'validaci' in k: fixed_k = 'Responsable de la validación'
        new_d[fixed_k] = v
        
    c.execute("UPDATE nucleus_data SET data_json = ? WHERE key_value = '29/9/2026 15:41:05'", (json.dumps(new_d, ensure_ascii=False),))
    db.commit()
    print("Fixed keys for 15:41:05")
