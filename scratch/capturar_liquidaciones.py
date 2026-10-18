# -*- coding: utf-8 -*-
"""Captura la respuesta de los endpoints de liquidaciones para comparar antes/después.

Uso: python scratch/capturar_liquidaciones.py salida.json
Trabaja sobre una COPIA fresca de la base para que el estado sea reproducible.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
BASE = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
SNAPSHOT = os.path.join(os.environ['TEMP'], 'snapshot_liquidaciones.db')
shutil.copy2(BASE, SNAPSHOT)
os.environ['DATABASE_URL'] = 'sqlite:///' + SNAPSHOT.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402

app = create_app()
salida = {}
with app.test_client() as c:
    with c.session_transaction() as s:
        s['user_id'] = 2
        s['username'] = 'hvargas'
        s['rol'] = 'zeno'
        s['current_proyecto_id'] = 14
        s['current_proyecto_nombre'] = 'FLM - ENTEL'
    for ruta in ('/liquidaciones/api/registros', '/refacturable/api/registros'):
        c.get(ruta)                      # calentar (puede crear numeraciones)
        r = c.get(ruta)
        cuerpo = r.get_data()
        salida[ruta] = {
            'code': r.status_code,
            'bytes': len(cuerpo),
            'sha': hashlib.sha256(cuerpo).hexdigest(),
            'registros': len(json.loads(cuerpo).get('registros', [])) if r.status_code == 200 else None,
        }
destino = sys.argv[1] if len(sys.argv) > 1 else 'captura.json'
with open(destino, 'w', encoding='utf-8') as f:
    json.dump(salida, f, ensure_ascii=False, indent=2)
print(json.dumps(salida, ensure_ascii=False, indent=2))
