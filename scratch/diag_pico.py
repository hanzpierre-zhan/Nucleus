# -*- coding: utf-8 -*-
"""Atribucion del pico de memoria de la peticion real a '/'."""
import os
import sys
import threading
import tracemalloc

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
URL = sys.argv[1] if len(sys.argv) > 1 else '/'

with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2; s['username'] = 'hvargas'; s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14; s['current_proyecto_nombre'] = 'FLM - ENTEL'
    c.get(URL)

    mejor = {'pico': 0, 'snap': None}
    parar = threading.Event()

    def vigilar():
        while not parar.is_set():
            actual = tracemalloc.get_traced_memory()[1]
            if actual > mejor['pico']:
                mejor['pico'] = actual
                mejor['snap'] = tracemalloc.take_snapshot()

    tracemalloc.start(25)
    hilo = threading.Thread(target=vigilar, daemon=True)
    hilo.start()
    r = c.get(URL)
    parar.set(); hilo.join(timeout=2)
    tracemalloc.stop()

    print(f'{URL}: {len(r.data)/1048576:.1f} MB, pico {mejor["pico"]/1048576:.1f} MB')
    total = 0
    for stat in mejor['snap'].statistics('traceback')[:15]:
        tb = stat.traceback[0]
        arch = tb.filename.split(chr(92))[-1]
        total += stat.size
        print(f'{stat.size/1048576:7.2f} MB  {arch}:{tb.lineno}')
    print(f'(suma top: {total/1048576:.1f} MB)')
