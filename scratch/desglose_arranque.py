# -*- coding: utf-8 -*-
"""Reparto del arranque en frío: import pesado vs create_app()."""
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

import importlib  # noqa: E402

PESADOS = ['pandas', 'PIL', 'PIL.Image', 'openpyxl', 'requests', 'boto3',
           'sqlalchemy', 'flask', 'werkzeug', 'numpy', 'dateutil', 'pytz']


def crono(etiqueta, t0):
    t = time.perf_counter()
    print(f'{etiqueta:26} {(t - t0) * 1000:8.0f} ms')
    return t


t = time.perf_counter(); t0 = t
for nombre in PESADOS:
    t = time.perf_counter()
    try:
        importlib.import_module(nombre)
        print(f'  import {nombre:12} {(time.perf_counter() - t) * 1000:7.0f} ms')
    except Exception as e:
        print(f'  import {nombre:12} NO ({type(e).__name__})')

from app import create_app  # noqa: E402

t = time.perf_counter()
create_app()
print(f'{"create_app() (steady)":26} {(time.perf_counter() - t) * 1000:8.0f} ms')
