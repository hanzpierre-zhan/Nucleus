# -*- coding: utf-8 -*-
"""Equivalencia de /api/sites/nombres (antes vs ahora)."""
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
from models import NucleusData, Proyecto  # noqa: E402

app = create_app()

CLAVES = (
    ('SITE', ('NOMBRE', 'NOMBRE SITE', 'NOMBRE DE SITE', 'NOMBRE DEL SITE')),
    ('Cotizaciones', ('NOMBRE SITE', 'NOMBRE DE SITE', 'NOMBRE DEL SITE')),
    ('Rendicion', ('NOMBRE DE SITE', 'NOMBRE DEL SITE', 'NOMBRE SITE')),
)


def antes():
    nombres = set()

    def _extraer(datos, claves):
        for clave in claves:
            for k in datos:
                if str(k or '').strip().upper() == clave:
                    valor = str(datos.get(k) or '').strip()
                    if valor:
                        nombres.add(valor)
                    return

    for nombre_proyecto, claves in CLAVES:
        proyecto = Proyecto.query.filter_by(nombre=nombre_proyecto).first()
        if not proyecto:
            continue
        for reg in NucleusData.query.filter_by(proyecto_id=proyecto.id).yield_per(500):
            try:
                datos = json.loads(reg.data_json or '{}')
            except (ValueError, TypeError):
                continue
            if isinstance(datos, dict):
                _extraer(datos, claves)
    return nombres


def ahora():
    nombres = set()
    pendiente = object()

    def _clave_nombre(datos, claves):
        por_clave = {}
        for k in datos:
            por_clave.setdefault(str(k or '').strip().upper(), k)
        for clave in claves:
            k = por_clave.get(clave)
            if k is not None:
                return k
        return None

    for nombre_proyecto, claves in CLAVES:
        proyecto = Proyecto.query.filter_by(nombre=nombre_proyecto).first()
        if not proyecto:
            continue
        columna_por_claves = {}
        filas = db.session.query(NucleusData.data_json).filter_by(
            proyecto_id=proyecto.id).yield_per(500)
        for (data_json,) in filas:
            try:
                datos = json.loads(data_json or '{}')
            except (ValueError, TypeError):
                continue
            if not isinstance(datos, dict):
                continue
            firma = tuple(datos)
            clave = columna_por_claves.get(firma, pendiente)
            if clave is pendiente:
                clave = _clave_nombre(datos, claves)
                columna_por_claves[firma] = clave
            if clave is not None:
                valor = str(datos.get(clave) or '').strip()
                if valor:
                    nombres.add(valor)
    return nombres


with app.app_context():
    t = time.perf_counter(); a = antes(); t_antes = (time.perf_counter() - t) * 1000
    t = time.perf_counter(); b = ahora(); t_ahora = (time.perf_counter() - t) * 1000
    print(f'antes {t_antes:7.0f} ms  ({len(a)} nombres)')
    print(f'ahora {t_ahora:7.0f} ms  ({len(b)} nombres)')
    print('conjunto idéntico:', a == b)
    print('lista ordenada idéntica:', sorted(a) == sorted(b))
