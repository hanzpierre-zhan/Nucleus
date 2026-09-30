import sqlite3, json

db = sqlite3.connect('nucleus.db')
c = db.cursor()

# Compare AEROPUERTO (broken) vs CENTRO SUR (working)
keys_to_check = ['29/9/2026 15:41:05', '29/9/2026 15:42:33']

for kv in keys_to_check:
    c.execute("SELECT data_json FROM nucleus_data WHERE key_value = ?", (kv,))
    row = c.fetchone()
    if row:
        d = json.loads(row[0])
        print(f"\n=== {kv} ===")
        print(f"  ESTADO: {repr(d.get('ESTADO', 'NOT FOUND'))}")
        print(f"  Nombre de site: {repr(d.get('Nombre de site', 'NOT FOUND'))}")
        
        # Check if there are any non-printable characters in the key names
        bad_keys = []
        for k in d.keys():
            if any(ord(ch) < 32 or (127 < ord(ch) < 160) for ch in k):
                bad_keys.append(repr(k))
        if bad_keys:
            print(f"  BAD KEYS with control chars: {bad_keys}")
        else:
            print(f"  All keys clean")
            
        # Print data as JSON exactly as Flask would
        js = json.dumps(d, ensure_ascii=False)
        # Check for any issue
        reparsed = json.loads(js)
        print(f"  JSON round-trip OK: {set(reparsed.keys()) == set(d.keys())}")
        print(f"  Keys count: {len(d.keys())}")
        print(f"  Has CODIGO DEPOSITO: {'CODIGO DEPOSITO' in d}")
