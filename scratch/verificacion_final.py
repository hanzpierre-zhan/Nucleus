# -*- coding: utf-8 -*-
"""Comprobaciones finales: qué módulos pesados quedan en el arranque y coste real
de `Proyecto.query.filter_by(nombre=...)` (el patrón repetido ~100 veces)."""
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
print('módulos cargados en el arranque:')
for nombre in ('pandas', 'numpy', 'openpyxl', 'boto3', 'PIL', 'pillow_heif'):
    print(f'   {nombre:12} {"SÍ" if nombre in sys.modules else "no"}')

with app.app_context():
    from db import db  # noqa: E402
    from models import Proyecto  # noqa: E402
    from sqlalchemy import event  # noqa: E402
    sql = {'n': 0}
    event.listen(db.engine, 'before_cursor_execute', lambda *a, **k: sql.__setitem__('n', sql['n'] + 1))
    Proyecto.query.filter_by(nombre='FLM - ENTEL').first()  # calentar
    sql['n'] = 0
    t = time.perf_counter()
    for _ in range(100):
        Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
    total = (time.perf_counter() - t) * 1000
    print(f'100 x filter_by(nombre): {total:.1f} ms ({total / 100:.3f} ms cada uno), {sql["n"]} SQL')
    print('proyectos en la tabla:', Proyecto.query.count())
