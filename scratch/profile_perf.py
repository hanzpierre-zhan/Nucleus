# -*- coding: utf-8 -*-
"""Perfila con cProfile los endpoints mas lentos."""
import cProfile
import io
import os
import pstats
import sys

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
URL = sys.argv[1] if len(sys.argv) > 1 else '/analytics'

with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2; s['username'] = 'hvargas'; s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14; s['current_proyecto_nombre'] = 'FLM - ENTEL'
    c.get(URL)  # calentar
    pr = cProfile.Profile()
    pr.enable()
    r = c.get(URL)
    pr.disable()
    print('URL', URL, 'status', r.status_code, 'bytes', len(r.data))
    st = pstats.Stats(pr, stream=sys.stdout).sort_stats('cumulative')
    st.print_stats(25)
