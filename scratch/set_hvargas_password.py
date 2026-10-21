import sqlite3
from werkzeug.security import generate_password_hash

NUEVO = sys_hash = None
import sys
NUEVO = sys.argv[1] if len(sys.argv) > 1 else 'zeno123'
c = sqlite3.connect('nucleus.db')
c.execute("update usuarios set password_hash=? where username='hvargas'", (generate_password_hash(NUEVO),))
c.commit()
print('ok', c.execute("select username, substr(password_hash,1,30) from usuarios where username='hvargas'").fetchone())
