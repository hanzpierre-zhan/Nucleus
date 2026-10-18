# -*- coding: utf-8 -*-
"""Inspecciona la config de la DB de tests (mismo entorno que conftest)."""
import os
import sys
import tempfile

BASE = r'C:\Mega\Proyect\Nucleus'
sys.path.insert(0, BASE)
_TMP = tempfile.mkdtemp(prefix='nucleus_inspect_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(_TMP, 'test.db').replace('\\', '/')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'test-secret')

from config import TestingConfig  # noqa: E402


class TestConfig(TestingConfig):
    EVIDENCIA_DIR = os.path.join(_TMP, 'evidencia')
    SQLALCHEMY_ENGINE_OPTIONS = {}


from app import create_app  # noqa: E402
from db import db  # noqa: E402
from models import AppConfig, NucleusData, Proyecto  # noqa: E402

app = create_app(TestConfig)
with app.app_context():
    db.create_all()
    for p in Proyecto.query.order_by(Proyecto.id).all():
        pk = AppConfig.query.filter_by(proyecto_id=p.id, clave='primary_key').first()
        mc = AppConfig.query.filter_by(proyecto_id=p.id, clave='manual_columns').first()
        n = NucleusData.query.filter_by(proyecto_id=p.id).count()
        print(f'id={p.id:3} {p.nombre!r:34} rows={n:5} pk={pk.valor if pk else None!r}')
        if mc:
            import json
            cols = [c['nombre'] for c in json.loads(mc.valor)]
            print(f'      manual_columns({len(cols)}): {cols[:6]}...')
