# -*- coding: utf-8 -*-
"""Captura la respuesta de una ruta GET sobre una COPIA fresca de la base.

Uso: python scratch/capturar_ruta.py <salida.json> <ruta> [ruta ...]
"""
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
BASE = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
SNAPSHOT = os.path.join(os.environ['TEMP'], 'snapshot_captura.db')
shutil.copy2(BASE, SNAPSHOT)
os.environ['DATABASE_URL'] = 'sqlite:///' + SNAPSHOT.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
salida = {'rutas': {}}
with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2
        s['username'] = 'hvargas'
        s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14
        s['current_proyecto_nombre'] = 'FLM - ENTEL'
    for ruta in sys.argv[2:]:
        c.get(ruta)
        r = c.get(ruta)
        cuerpo = r.get_data()
        salida['rutas'][ruta] = {
            'code': r.status_code,
            'bytes': len(cuerpo),
            'sha': hashlib.sha256(cuerpo).hexdigest(),
        }
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    json.dump(salida, f, ensure_ascii=False, indent=2)
print(json.dumps(salida['rutas'], ensure_ascii=False, indent=2))
