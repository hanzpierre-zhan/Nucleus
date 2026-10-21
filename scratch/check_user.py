import sqlite3
c = sqlite3.connect('nucleus.db')
row = c.execute("select id, username, password_hash, rol from usuarios where username='hvargas'").fetchone()
print(row)
