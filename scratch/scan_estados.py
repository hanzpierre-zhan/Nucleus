# -*- coding: utf-8 -*-
"""Mide el código de respuesta de cada ruta GET sin parámetros, para decidir
cuáles entran en el barrido de pruebas (se excluyen las de red/mutación)."""
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

SALTAR = {'/api/rendicion/sync'}  # descarga externa

app = create_app()
rutas = sorted({str(r) for r in app.url_map.iter_rules()
                if 'GET' in r.methods and '<' not in str(r)
                and not str(r).startswith(('/static', '/logout'))})

with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2
        s['username'] = 'hvargas'
        s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14
        s['current_proyecto_nombre'] = 'FLM - ENTEL'
    for ruta in rutas:
        if ruta in SALTAR:
            print('%4s %8s  %s  (SALTADA)' % ('--', '--', ruta))
            continue
        try:
            t0 = time.perf_counter()
            r = c.get(ruta)
            print('%4d %8.1f  %s  %sKB' % (r.status_code, (time.perf_counter() - t0) * 1000,
                                           ruta, len(r.data) // 1024))
        except Exception as error:  # noqa: BLE001
            print('%4s %8s  %s  (ERROR %s)' % ('exc', '--', ruta, type(error).__name__))
