# -*- coding: utf-8 -*-
"""A/B del arranque en frío: con `import pandas` (antes) vs perezoso (ahora).

Uso: python scratch/cold_ab.py [con|sin]
"""
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

modo = (sys.argv[1] if len(sys.argv) > 1 else 'sin').lower()

t = time.perf_counter()
if modo == 'con':
    import pandas  # noqa: F401  (lo que hacían los 10 módulos en el arranque)
from app import create_app  # noqa: E402
t_import = (time.perf_counter() - t) * 1000
t = time.perf_counter()
create_app()
t_create = (time.perf_counter() - t) * 1000
print(f'{modo:4} | import app {t_import:7.0f} ms | create_app {t_create:7.0f} ms | total {t_import + t_create:7.0f} ms')
