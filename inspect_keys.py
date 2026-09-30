import sqlite3, json, sys

db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT data_json FROM nucleus_data WHERE key_value = '29/9/2026 15:41:05'")
row = c.fetchone()
if row:
    d = json.loads(row[0])
    # Print each key with its repr to see the exact bytes/chars
    for k, v in d.items():
        has_bad = any(ord(ch) > 127 for ch in k)
        if has_bad:
            print(f"BAD KEY: repr={repr(k)}")
        else:
            print(f"OK  KEY: {k}")
