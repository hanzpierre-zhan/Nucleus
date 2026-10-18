# -*- coding: utf-8 -*-
"""Diagnostico de GET /: SQL emitido y sitios de mayor asignacion de memoria."""
import os
import sys
import tracemalloc

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from sqlalchemy import event  # noqa: E402
from db import db  # noqa: E402
from app import create_app  # noqa: E402

app = create_app()
URL = sys.argv[1] if len(sys.argv) > 1 else '/'
SQLS = []

with app.app_context():
    event.listen(db.engine, 'before_cursor_execute',
                 lambda conn, cur, stmt, params, ctx, many: SQLS.append(stmt))

with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2; s['username'] = 'hvargas'; s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14; s['current_proyecto_nombre'] = 'FLM - ENTEL'
    c.get(URL)  # calentar caches
    SQLS.clear()
    tracemalloc.start(15)
    r = c.get(URL)
    snap = tracemalloc.take_snapshot()
    tracemalloc.stop()
    print(f'URL {URL} status {r.status_code} bytes {len(r.data)}')
    print(f'--- {len(SQLS)} sentencias SQL ---')
    for i, q in enumerate(SQLS, 1):
        print(f'{i:2}. {" ".join(q.split())[:130]}')
    print('--- top memoria ---')
    for stat in snap.statistics('lineno')[:15]:
        print(f'{stat.size/1048576:8.2f} MB  {stat.traceback[0].filename.split(chr(92))[-1]}:{stat.traceback[0].lineno}')
