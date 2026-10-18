# -*- coding: utf-8 -*-
"""Aisla el pico de '/' stubeando render_template y/o json.dumps."""
import json as _json
import os
import sys
import tracemalloc
from types import SimpleNamespace

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402
import blueprints.pages as P  # noqa: E402

app = create_app()
_render_real, _dumps_real = P.render_template, _json.dumps
P.json = SimpleNamespace(dumps=_json.dumps, loads=_json.loads)


def pico(cliente):
    cliente.get('/')
    tracemalloc.start()
    cliente.get('/')
    p = tracemalloc.get_traced_memory()[1] / 1048576
    tracemalloc.stop()
    return p


with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2; s['username'] = 'hvargas'; s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14; s['current_proyecto_nombre'] = 'FLM - ENTEL'

    print(f'1) completo .................... {pico(c):6.1f} MB')

    P.render_template = lambda *a, **k: '__x__'
    print(f'2) sin render (solo datos) ..... {pico(c):6.1f} MB')
    P.render_template = _render_real

    P.json = SimpleNamespace(
        dumps=lambda o, *a, **k: '[]' if isinstance(o, list) else _json.dumps(o, *a, **k),
        loads=_json.loads)
    print(f'3) sin json.dumps de la tabla .. {pico(c):6.1f} MB')
    P.json = SimpleNamespace(dumps=_json.dumps, loads=_json.loads)

    P.render_template = lambda *a, **k: '__x__'
    P.json = SimpleNamespace(
        dumps=lambda o, *a, **k: '[]' if isinstance(o, list) else _json.dumps(o, *a, **k),
        loads=_json.loads)
    print(f'4) sin render ni dumps ......... {pico(c):6.1f} MB')
    P.render_template, P.json = _render_real, SimpleNamespace(dumps=_json.dumps, loads=_json.loads)
