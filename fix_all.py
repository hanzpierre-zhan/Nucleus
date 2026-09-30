import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
rows = c.fetchall()

fixes = {
    'Tcnico beneficiario': 'Técnico beneficiario',
    'Nmero CM / PM / PLM': 'Número CM / PM / PLM',
    'Monto total del depsito': 'Monto total del depósito',
    'Tipo de depsito a realizar': 'Tipo de depósito a realizar',
    'Nmero de celular o CCI': 'Número de celular o CCI',
    'Responsable de la validacin': 'Responsable de la validación'
}

for key, data_json in rows:
    try:
        d = json.loads(data_json)
        needs_fix = False
        new_d = {}
        for k, v in d.items():
            fixed_k = k
            if '' in k:
                if 'T' in k and 'cnico' in k: fixed_k = 'Técnico beneficiario'
                elif 'N' in k and 'mero' in k and 'CM' in k: fixed_k = 'Número CM / PM / PLM'
                elif 'Monto' in k and 'p' in k and 'sito' in k: fixed_k = 'Monto total del depósito'
                elif 'Tipo' in k and 'p' in k and 'sito' in k: fixed_k = 'Tipo de depósito a realizar'
                elif 'N' in k and 'mero' in k and 'celular' in k: fixed_k = 'Número de celular o CCI'
                elif 'Responsable' in k and 'validaci' in k: fixed_k = 'Responsable de la validación'
                needs_fix = True
            elif k in fixes:
                fixed_k = fixes[k]
                needs_fix = True
            
            # also catch if they are exactly matching the broken strings without replacement char
            if k == 'Tcnico beneficiario':
                fixed_k = 'Técnico beneficiario'
                needs_fix = True
            
            new_d[fixed_k] = v
            
        if needs_fix:
            c.execute("UPDATE nucleus_data SET data_json = ? WHERE key_value = ?", (json.dumps(new_d, ensure_ascii=False), key))
            print(f"Fixed keys for {key}")
    except:
        pass

db.commit()
print("Done")
