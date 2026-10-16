import sqlite3
from werkzeug.security import generate_password_hash

DB = 'scratch/repro.db'
LEGAL_VERSION = '2026-10-09'
c = sqlite3.connect(DB)
cur = c.cursor()

def upsert_user(username, rol):
    row = cur.execute('select id from usuarios where username=?', (username,)).fetchone()
    h = generate_password_hash('zeno123')
    if row:
        uid = row[0]
        cur.execute('update usuarios set password_hash=?, rol=? where id=?', (h, rol, uid))
    else:
        cur.execute('insert into usuarios (username, password_hash, rol, nombre) values (?,?,?,?)',
                    (username, h, rol, username))
        uid = cur.lastrowid
    # conformidad vigente para saltar el paso de consentimiento
    cur.execute('delete from conformidad_usuario where usuario_id=?', (uid,))
    cur.execute('insert into conformidad_usuario (usuario_id, version, aceptado_en) values (?,?,datetime(\'now\'))',
                (uid, LEGAL_VERSION))
    return uid

zeno_id = upsert_user('zeno', 'zeno')
tadmin_id = upsert_user('t_admin', 'admin')
gestor_id = upsert_user('t_gestor', 'gestor')

# accesos para t_admin/t_gestor: FLM - ENTEL (1) y Rendicion (11)
for pid in (1, 11):
    for u in (tadmin_id, gestor_id):
        if not cur.execute('select 1 from accesos_proyecto where usuario_id=? and proyecto_id=?',
                           (u, pid)).fetchone():
            cur.execute('insert into accesos_proyecto (usuario_id, proyecto_id, restricciones) values (?,?,?)',
                        (u, pid, '{}'))

c.commit()
print('seeded. zeno_id=%s tadmin_id=%s' % (zeno_id, tadmin_id))
for r in cur.execute('select id, username, rol from usuarios order by id'):
    print('  ', r)
c.close()
