# -*- coding: utf-8 -*-
"""Mide el costo/beneficio de bajar el nivel de compresión de /api/admin/export_zip.

El ZIP de respaldo usa nivel 6 (por defecto). Menos nivel = más rápido pero el
archivo pesa más: aquí se mide tiempo y tamaño reales para cada nivel.
"""
import os
import sys
import time
import zipfile as _zip

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402
import blueprints.admin as admin  # noqa: E402


class ZipPorNivel(_zip.ZipFile):
    """ZipFile con el nivel de compresión fijado desde el banco."""
    nivel = 6

    def __init__(self, *args, **kwargs):
        kwargs['compresslevel'] = ZipPorNivel.nivel
        super().__init__(*args, **kwargs)


admin.zipfile.ZipFile = ZipPorNivel

app = create_app()
with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2
        s['username'] = 'hvargas'
        s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14
        s['current_proyecto_nombre'] = 'FLM - ENTEL'
    print(f'{"nivel":>5} {"ms":>8} {"MB":>8}')
    for nivel in (6, 3, 1, 0):
        ZipPorNivel.nivel = nivel
        c.get('/api/admin/export_zip')  # calentar
        tiempos = []
        tam = 0
        for _ in range(3):
            t0 = time.perf_counter()
            r = c.get('/api/admin/export_zip')
            tiempos.append((time.perf_counter() - t0) * 1000)
            tam = len(r.data)
        tiempos.sort()
        print(f'{nivel:5d} {tiempos[1]:8.1f} {tam/1048576:8.2f}')
