# -*- coding: utf-8 -*-
"""Cuánto cuesta la parte de código (no red) de /api/rendicion/sync."""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402
from db import db  # noqa: E402
from models import AppConfig, NucleusData, Proyecto  # noqa: E402

app = create_app()
with app.app_context():
    proy = Proyecto.query.filter_by(nombre='Rendicion').first()
    from services.rendicion_personal import indice_personal, completar_personal

    t = time.perf_counter()
    personal = indice_personal()
    print(f'indice_personal               {(time.perf_counter()-t)*1000:7.0f} ms')

    t = time.perf_counter()
    actualizados = 0
    n = 0
    for registro in NucleusData.query.filter_by(proyecto_id=proy.id).yield_per(500):
        anteriores = json.loads(registro.data_json or '{}')
        cruzados = completar_personal(dict(anteriores), personal)
        n += 1
        if cruzados['_PERSONAL_CRUCE']['estado'] in ('VERIFICADO', 'SIN DEPARTAMENTO EN PERSONAL'):
            if cruzados != anteriores:
                actualizados += 1
    print(f'bucle {n} filas (sin commit)   {(time.perf_counter()-t)*1000:7.0f} ms  cambios={actualizados}')
