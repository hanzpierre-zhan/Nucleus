import sqlite3
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT key_value, COUNT(*) FROM nucleus_data GROUP BY key_value HAVING COUNT(*) > 1")
dups = c.fetchall()
print('Duplicates:', dups)
