import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT data_json FROM nucleus_data WHERE key_value = '29/9/2026 15:41:05'")
row = c.fetchone()
d = json.loads(row[0])
for k in d.keys():
    print(repr(k))
