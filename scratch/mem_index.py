# -*- coding: utf-8 -*-
"""Descompone el pico de memoria de GET / por etapa."""
import json
import os
import sqlite3
import sys
import tracemalloc

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
PID = 14


def pico():
    _, p = tracemalloc.get_traced_memory()
    return p / 1048576


with app.app_context():
    con = sqlite3.connect(DB)
    filas = con.execute('select key_value, data_json from nucleus_data where proyecto_id=?', (PID,)).fetchall()

    tracemalloc.start()
    datos = [json.loads(dj) for _, dj in filas]
    print(f'1. decodificar {len(datos)} filas ......... pico {pico():7.1f} MB')

    tracemalloc.reset_peak()
    texto = json.dumps(datos, ensure_ascii=False, separators=(',', ':'))
    print(f'2. json.dumps ({len(texto)/1048576:.1f} MB str) ..... pico {pico():7.1f} MB')

    tracemalloc.reset_peak()
    with app.test_request_context('/'):
        from flask import render_template
        html = render_template('index.html',
                               data=texto, columns=json.dumps(['_key']), pk='NO_DEF',
                               manual_cols=json.dumps([]), column_layout=json.dumps([]),
                               column_layout_vistas=json.dumps({}), kpi_meta=json.dumps({}),
                               changed_keys=json.dumps([]), gen_tipo_map=json.dumps({}),
                               gen_tecnico_map=json.dumps({}), gen_zona_map=json.dumps({}),
                               wo_list=json.dumps([]), proyectos_list=[],
                               puede_coti=True, puede_rend=None, proy_actual=None,
                               current_proyecto_nombre='FLM - ENTEL', usuario='x', rol='zeno',
                               kpi_configs=[], personal_rendicion=None, extra_columns=[],
                               equipo_opciones=[])
    print(f'3. render_template ({len(html)/1048576:.1f} MB) ... pico {pico():7.1f} MB')
    tracemalloc.stop()
