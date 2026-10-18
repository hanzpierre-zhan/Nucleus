# -*- coding: utf-8 -*-
"""Aisla el pico de render_template: cuanto aporta el bloque `data` vs la plantilla."""
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

KW = dict(columns=json.dumps(['_key']), pk='NO_DEF', manual_cols=json.dumps([]),
          column_layout=json.dumps([]), column_layout_vistas=json.dumps({}),
          kpi_meta=json.dumps({}), changed_keys=json.dumps([]), gen_tipo_map=json.dumps({}),
          gen_tecnico_map=json.dumps({}), gen_zona_map=json.dumps({}), gen_saldo_map=json.dumps({}),
          wo_list=json.dumps([]), proyectos_list=[], puede_coti=True, puede_rend=None,
          proy_actual=None, current_proyecto_nombre='FLM - ENTEL', usuario='x', rol='zeno',
          kpi_configs=[], personal_rendicion=None, extra_columns=[], equipo_opciones=[])


def pico_mb():
    return tracemalloc.get_traced_memory()[1] / 1048576


with app.app_context():
    con = sqlite3.connect(DB)
    filas = con.execute('select data_json from nucleus_data where proyecto_id=?', (PID,)).fetchall()
    datos = [json.loads(f[0]) for f in filas]
    grande = json.dumps(datos, ensure_ascii=False, separators=(',', ':'))
    print(f'data json: {len(grande)/1048576:.1f} MB')

    with app.test_request_context('/'):
        from flask import render_template
        # A) con el bloque grande
        tracemalloc.start()
        html = render_template('index.html', data=grande, **KW)
        p_grande = pico_mb()
        tracemalloc.stop()
        print(f'A) render con data grande ({len(html)/1048576:.1f} MB out): pico {p_grande:.1f} MB')

        # B) con data vacio (misma plantilla, mismas llaves)
        tracemalloc.start()
        html2 = render_template('index.html', data='[]', **KW)
        p_vacio = pico_mb()
        tracemalloc.stop()
        print(f'B) render con data vacio  ({len(html2)/1048576:.2f} MB out): pico {p_vacio:.1f} MB')
        print(f'=> el bloque data aporta ~{p_grande - p_vacio:.1f} MB al pico')
