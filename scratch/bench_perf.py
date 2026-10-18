# -*- coding: utf-8 -*-
"""Banco de rendimiento de Nucleus contra una COPIA de nucleus.db.

Mide por endpoint: tiempo de pared (media), numero de SQL, tamano de respuesta
y pico de memoria con tracemalloc. Uso:  python bench.py [endpoint ...]
"""
import os
import shutil
import sys
import tempfile
import time
import tracemalloc

SRC = r'C:\Mega\Proyect\Nucleus\nucleus.db'
TMP = os.environ.get('TEMP', tempfile.gettempdir())
DB = os.path.join(TMP, 'bench_nucleus.db')
sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
if not os.path.exists(DB) or os.path.getmtime(DB) < os.path.getmtime(SRC):
    shutil.copy2(SRC, DB)
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ.setdefault('FLASK_ENV', 'testing')

from sqlalchemy import event  # noqa: E402
from db import db  # noqa: E402
from app import create_app  # noqa: E402

app = create_app()

CONTADOR = {'n': 0}
with app.app_context():
    event.listen(db.engine, 'before_cursor_execute', lambda *a, **k: CONTADOR.__setitem__('n', CONTADOR['n'] + 1))

ENDPOINTS = sys.argv[1:] or [
    '/',
    '/analytics',
    '/analytics/rendicion',
    '/analytics/cobranza',
    '/api/detalle/opciones?proyecto=14',
    '/api/sites',
    '/api/wos_flm',
    '/api/combustible/por_wo?wo=CM-20260814-00000160',
    '/personal/asistencia',
    '/api/asistencia/contexto',
    '/api/asistencia/dia',
]


def medir(client, url, repes=5):
    # Calentamiento (rellena caches por request)
    client.get(url)
    # 1) Tiempo y SQL sin tracemalloc (no lo distorsiona)
    tiempos = []
    tam = 0
    q = 0
    code = 0
    for _ in range(repes):
        CONTADOR['n'] = 0
        t0 = time.perf_counter()
        r = client.get(url)
        tiempos.append((time.perf_counter() - t0) * 1000)
        tam = len(r.data)
        q = CONTADOR['n']
        code = r.status_code
    # 2) Memoria en una pasada aparte
    tracemalloc.start()
    client.get(url)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tiempos.sort()
    return tiempos[len(tiempos) // 2], q, tam, pico, code


with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2
        s['username'] = 'hvargas'
        s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14
        s['current_proyecto_nombre'] = 'FLM - ENTEL'
    print(f'{"endpoint":50} {"ms":>8} {"sql":>6} {"KB":>8} {"picoMB":>8}  code')
    for url in ENDPOINTS:
        ms, q, tam, pico, code = medir(c, url)
        print(f'{url[:50]:50} {ms:8.1f} {q:6d} {tam/1024:8.0f} {pico/1048576:8.1f}  {code}')
