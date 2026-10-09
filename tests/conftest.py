# -*- coding: utf-8 -*-
"""Harness de tests de la auditoría (bug-hunt).

Aísla la base de datos en un SQLite temporal ANTES de importar `app`, de modo
que ni la instancia a nivel de módulo (`app = create_app()` en app.py) ni los
tests toquen la base real `nucleus.db`.

No modifica el código fuente de la aplicación: solo lo importa y lo ejercita.
"""
import os
import sys
import tempfile

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Aislamiento: DB temporal + dir de evidencia temporal ────────────────────
_TMP_DIR = tempfile.mkdtemp(prefix='nucleus_bughunt_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(_TMP_DIR, 'test.db').replace('\\', '/')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'test-secret')

import pytest  # noqa: E402
from config import TestingConfig  # noqa: E402


class TestConfig(TestingConfig):
    """TestingConfig con rutas de datos redirigidas al directorio temporal."""
    EVIDENCIA_DIR = os.path.join(_TMP_DIR, 'evidencia')
    SQLALCHEMY_ENGINE_OPTIONS = {}


def make_app():
    """Crea una app nueva (usa la DB temporal)."""
    from app import create_app
    return create_app(TestConfig)


@pytest.fixture(scope='session')
def app():
    application = make_app()
    with application.app_context():
        from db import db
        db.create_all()
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(app):
    """Cliente ya autenticado como zeno (usuario creado por las migraciones)."""
    c = app.test_client()
    r = c.post('/login', data={'username': 'zeno', 'password': 'zeno123', 'legal_accept': '1'})
    if r.status_code == 200 and b'name="consent_step"' in r.data:
        r = c.post('/login', data={'consent_step': '1', 'legal_accept': '1'})
    assert r.status_code in (301, 302), 'No se pudo iniciar sesión como zeno'
    return c
