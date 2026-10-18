# -*- coding: utf-8 -*-
"""Recorre todas las rutas GET (sin parámetros) y cuenta las consultas SQL.

En producción la base es Postgres remoto (Neon): cada consulta cuesta una ida y
vuelta de red, así que el número de SQL pesa más que los milisegundos locales.
Ordena de mayor a menor para detectar patrones N+1.
"""
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from sqlalchemy import event  # noqa: E402
from db import db  # noqa: E402
from app import create_app  # noqa: E402

app = create_app()
CONTADOR = {'n': 0}
with app.app_context():
    event.listen(db.engine, 'before_cursor_execute',
                 lambda *a, **k: CONTADOR.__setitem__('n', CONTADOR['n'] + 1))

OMITIR = ('/logout', '/static')
rutas = sorted({str(r) for r in app.url_map.iter_rules()
                if 'GET' in r.methods and '<' not in str(r)
                and not any(str(r).startswith(o) for o in OMITIR)})

resultados = []
with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2
        s['username'] = 'hvargas'
        s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14
        s['current_proyecto_nombre'] = 'FLM - ENTEL'
    for ruta in rutas:
        try:
            c.get(ruta)  # calentar (caches por request, numeraciones, etc.)
            CONTADOR['n'] = 0
            t0 = time.perf_counter()
            r = c.get(ruta)
            ms = (time.perf_counter() - t0) * 1000
            resultados.append((CONTADOR['n'], ms, len(r.data), r.status_code, ruta))
        except Exception as error:  # noqa: BLE001
            resultados.append((-1, 0, 0, 0, f'{ruta}  (ERROR {type(error).__name__})'))

resultados.sort(reverse=True)
print(f'{"sql":>5} {"ms":>8} {"KB":>8}  code  ruta')
for q, ms, tam, code, ruta in resultados[:40]:
    print(f'{q:5d} {ms:8.1f} {tam/1024:8.0f}  {code:4}  {ruta[:80]}')
