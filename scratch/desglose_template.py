# -*- coding: utf-8 -*-
"""Desglose de tiempos reales de /api/import/manual_template."""
import io
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


def crono(etiqueta, t0):
    t = time.perf_counter()
    print(f'{etiqueta:34} {(t-t0)*1000:7.0f} ms')
    return t


app = create_app()
with app.app_context():
    t = time.perf_counter()
    t0 = time.perf_counter(); import pandas as pd; t = crono('import pandas (1a vez)', t)
    pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
    t = crono('query proyecto', t)
    cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    manual_cols = [mc['nombre'] for mc in json.loads(cfg.valor)]
    columnas_manual = manual_cols[:16] if manual_cols else [f'C{i}' for i in range(16)]
    t = crono('config + columnas', t)
    rows = NucleusData.query.filter_by(proyecto_id=pid).all()
    t = crono(f'query {len(rows)} filas (ORM)', t)
    detalle = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
    parsed = [(r.key_value, json.loads(r.data_json)) for r in rows]
    t = crono('json.loads todas', t)
    data = {'pk': [k for k, _ in parsed]}
    for c in detalle + columnas_manual:
        data[c] = [str((d.get(c) or '')) for _, d in parsed]
    t = crono('armar 26 listas', t)
    df = pd.DataFrame(data)
    t = crono('pd.DataFrame', t)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        df.to_excel(w, index=False, sheet_name='P')
        ws = w.sheets['P']; ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
        t = crono('to_excel', t)
    t = crono('cerrar writer (save)', t)
    print(f'bytes xlsx: {len(out.getvalue())}')
