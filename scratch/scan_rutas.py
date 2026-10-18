# -*- coding: utf-8 -*-
"""Recorre todas las rutas GET del app y mide tiempo/peso para hallar cuellos."""
import os
import sys
import time
import tracemalloc

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
rutas = sorted({str(r) for r in app.url_map.iter_rules()
                if 'GET' in r.methods and '<' not in str(r) and not str(r).startswith('/static')})

resultados = []
with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2; s['username'] = 'hvargas'; s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14; s['current_proyecto_nombre'] = 'FLM - ENTEL'
    for ruta in rutas:
        try:
            c.get(ruta)  # calentar
            t0 = time.perf_counter()
            r = c.get(ruta)
            ms = (time.perf_counter() - t0) * 1000
            resultados.append((ms, len(r.data), r.status_code, ruta))
        except Exception as e:  # noqa: BLE001
            resultados.append((-1, 0, 0, f'{ruta}  (ERROR {type(e).__name__})'))

resultados.sort(reverse=True)
print(f'{"ms":>9} {"KB":>9}  code  ruta')
for ms, tam, code, ruta in resultados[:40]:
    print(f'{ms:9.1f} {tam/1024:9.0f}  {code:4}  {ruta[:80]}')
