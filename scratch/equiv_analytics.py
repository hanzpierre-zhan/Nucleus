# -*- coding: utf-8 -*-
"""Equivalencia de /analytics (indicadores antes vs ahora)."""
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402
from db import db  # noqa: E402
from models import NucleusData, Proyecto  # noqa: E402
from services import dashboard_integratel as D  # noqa: E402

_PATRON_NO_ALNUM = re.compile(r'[^a-z0-9]')
_PATRON_FECHA = re.compile(r'^(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})')
_PATRON_TIPO_WO = re.compile(r'^(PLM|PM|CM)(?:\b|[-_0-9])')


@lru_cache(maxsize=8192)
def _norm(texto):
    return _PATRON_NO_ALNUM.sub('', unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower())


def normalizar(v):
    v = v or ''
    if not isinstance(v, str):
        v = str(v)
    return _norm(v)


def fecha(value):
    text = str(value or '').strip()
    match = _PATRON_FECHA.match(text)
    if not match:
        return None
    for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(match[1], pattern).date()
        except ValueError:
            pass
    return None


def indicadores_antes(rows, hoy=None):
    """Copia literal de la versión anterior."""
    hoy = hoy or date.today()
    actual = hoy.strftime('%Y-%m')
    meses, departamentos, sites, fases = Counter(), Counter(), Counter(), Counter()
    tipos = defaultdict(Counter)
    produccion = backlog = abiertos_actual = sin_fecha = futuros = total = 0
    detalle = []
    for row in rows:
        total += 1
        fields = {}
        for key, value in row.items():
            normalized = normalizar(key)
            if normalized not in fields or fields[normalized] in (None, ''):
                fields[normalized] = value

        def valor(*keys):
            for k in keys:
                actual_v = fields.get(normalizar(k))
                if actual_v not in (None, ''):
                    return actual_v
            return ''

        phase = str(valor('OPERATE PHASE', 'OPHERATE PHASE')).strip().lower()
        creation = fecha(valor('Fecha de creación (WO Creation date)', 'FECHA DE CREACION', 'FECHA CREACION', 'WO CREATION DATE', 'CREATION TIME', 'CREATE TIME'))
        month = creation.strftime('%Y-%m') if creation else None
        wo = str(valor('NÚMERO DE WO', 'NUMERO WO', 'WO NUMBER', '_key')).strip()
        match = _PATRON_TIPO_WO.match(str(valor('TIPO WO') or wo).upper())
        tipo = match.group(1) if match else 'Otros'
        dept = str(valor('DEPARTAMENTO')).strip() or 'Sin departamento'
        site = str(valor('NOMBRE DE SITE', 'NOMBRE SITE', 'SITE NAME', 'SITE')).strip() or 'Sin site'
        if phase == 'close':
            grupo = 'Producción'
            produccion += 1
            departamentos[dept] += 1
            sites[site] += 1
            if month: meses[month] += 1
        else:
            fases[phase or 'Sin fase'] += 1
            if month is None: grupo = 'Sin fecha'
            elif month < actual: grupo = 'Backlog'; backlog += 1
            elif month == actual: grupo = 'En atención'; abiertos_actual += 1
            else: grupo = 'Fecha futura'; futuros += 1
        if month is None: sin_fecha += 1
        tipos[grupo][tipo] += 1
        detalle.append({'wo': wo, 'tipo': tipo, 'mes': month or '',
                        'fecha': creation.isoformat() if creation else '',
                        'tarea': str(valor('Tipo tarea', 'TIPO DE TAREA', 'TIPO TAREA')).strip() or 'Sin tipo de tarea',
                        'personal': str(valor('Nombre de personal FLM asignado', 'PERSONAL FLM ASIGNADO', 'FLM ASIGNADO', 'TECNICO ASIGNADO')).strip() or 'Sin personal asignado',
                        'prioridad': str(valor('Prioridad del Site', 'PRIORIDAD SITE')).strip() or 'Sin prioridad',
                        'fault': str(valor('Fault Level', 'NIVEL DE FALLA')).strip() or 'Sin Fault Level',
                        'departamento': dept, 'site': site, 'fase': phase or 'Sin fase', 'grupo': grupo})
    return {'mes_actual': actual, 'total': total, 'produccion': produccion, 'backlog': backlog,
            'en_atencion': abiertos_actual, 'sin_fecha': sin_fecha, 'futuros': futuros,
            'meses': dict(sorted(meses.items())), 'departamentos': departamentos.most_common(),
            'sites': sites.most_common(), 'tipos': {k: dict(v) for k, v in tipos.items()},
            'fases': fases.most_common(), 'detalle': detalle}


def filas(pid):
    for fila in NucleusData.query.filter_by(proyecto_id=pid).order_by(NucleusData.id).yield_per(500):
        try:
            datos = json.loads(fila.data_json)
        except (ValueError, TypeError):
            continue
        if isinstance(datos, dict):
            datos['_key'] = fila.key_value
            yield datos


import time  # noqa: E402

app = create_app()
with app.app_context():
    proy = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
    HOY = date(2026, 10, 17)
    t = time.perf_counter(); a = indicadores_antes(filas(proy.id), HOY); t_antes = (time.perf_counter() - t) * 1000
    t = time.perf_counter(); b = D.indicadores(filas(proy.id), HOY); t_ahora = (time.perf_counter() - t) * 1000
    print(f'antes {t_antes:7.0f} ms  total={a["total"]}')
    print(f'ahora {t_ahora:7.0f} ms  total={b["total"]}')
    print('resultado idéntico:', a == b)
    if a != b:
        for k in a:
            if a[k] != b[k]:
                print('  DIF en', k)
