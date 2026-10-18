# -*- coding: utf-8 -*-
"""Equivalencia de /api/catalogos/autocompletar (antes vs ahora)."""
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
from models import NucleusData  # noqa: E402
from services.utilidades import get_menu_proyectos  # noqa: E402
from services.recursos_flm import normalizar  # noqa: E402

app = create_app()
UID, ROL = 2, 'zeno'


def antes(ids):
    sites = {}
    for fila in NucleusData.query.filter(NucleusData.proyecto_id.in_(ids)).all():
        try:
            datos = json.loads(fila.data_json or '{}')
        except (ValueError, TypeError):
            continue
        for campo, valor in datos.items():
            if normalizar(campo) in ('site', 'nombresite', 'nombredesite', 'nombredelsite', 'sitename') \
                    and isinstance(valor, str) and valor.strip():
                sites.setdefault(valor.strip().casefold(), valor.strip())
    return sites


def ahora(ids):
    sites = {}
    claves_site = ('site', 'nombresite', 'nombredesite', 'nombredelsite', 'sitename')
    es_clave_site = {}
    filas = (db.session.query(NucleusData.data_json)
             .filter(NucleusData.proyecto_id.in_(ids)).yield_per(1000))
    for (data_json,) in filas:
        try:
            datos = json.loads(data_json or '{}')
        except (ValueError, TypeError):
            continue
        for campo, valor in datos.items():
            aceptado = es_clave_site.get(campo)
            if aceptado is None:
                aceptado = normalizar(campo) in claves_site
                es_clave_site[campo] = aceptado
            if aceptado and isinstance(valor, str) and valor.strip():
                sites.setdefault(valor.strip().casefold(), valor.strip())
    return sites


with app.app_context():
    permitidos = get_menu_proyectos(UID, ROL)
    ids = [p.id for p in permitidos if p.nombre == 'SITE']
    print('ids SITE:', ids)
    t = time.perf_counter(); a = antes(ids); t_antes = (time.perf_counter() - t) * 1000
    t = time.perf_counter(); b = ahora(ids); t_ahora = (time.perf_counter() - t) * 1000
    print(f'antes {t_antes:7.0f} ms  ({len(a)} sites)')
    print(f'ahora {t_ahora:7.0f} ms  ({len(b)} sites)')
    print('mismo diccionario:', a == b)
