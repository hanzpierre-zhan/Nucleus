# -*- coding: utf-8 -*-
"""Captura una instantanea de tracemalloc EN el pico del render."""
import json
import os
import sqlite3
import sys
import threading
import time
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

with app.app_context():
    con = sqlite3.connect(DB)
    datos = [json.loads(f[0]) for f in con.execute(
        'select data_json from nucleus_data where proyecto_id=?', (PID,)).fetchall()]
    grande = json.dumps(datos, ensure_ascii=False, separators=(',', ':'))

    with app.test_request_context('/'):
        from flask import render_template
        mejor = {'pico': 0, 'snap': None}

        def vigilar():
            while not parar.is_set():
                actual = tracemalloc.get_traced_memory()[1]
                if actual > mejor['pico']:
                    mejor['pico'] = actual
                    mejor['snap'] = tracemalloc.take_snapshot()

        parar = threading.Event()
        tracemalloc.start(20)
        hilo = threading.Thread(target=vigilar, daemon=True)
        hilo.start()
        html = render_template('index.html', data=grande, **KW)
        parar.set(); hilo.join(timeout=2)
        tracemalloc.stop()
        print(f'pico {mejor["pico"]/1048576:.1f} MB, salida {len(html)/1048576:.1f} MB')
        print('--- top asignaciones en el pico ---')
        for stat in mejor['snap'].statistics('traceback')[:12]:
            tb = stat.traceback[0]
            print(f'{stat.size/1048576:7.2f} MB  {tb.filename.split(chr(92))[-1]}:{tb.lineno}')
