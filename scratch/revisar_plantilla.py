"""Revisa qué devuelve /api/import/manual_template en cada módulo (copia de la base real)."""
import os
import shutil
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

_tmp = tempfile.mkdtemp(prefix='nucleus_tpl_')
copia = os.path.join(_tmp, 'preview.db')
shutil.copy2(os.path.join(BASE, 'nucleus.db'), copia)
os.environ['DATABASE_URL'] = 'sqlite:///' + copia.replace('\\', '/')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'preview-secret')

from config import TestingConfig  # noqa: E402


class Config(TestingConfig):
    EVIDENCIA_DIR = os.path.join(_tmp, 'evidencia')
    SQLALCHEMY_ENGINE_OPTIONS = {}


from app import create_app  # noqa: E402
from db import db  # noqa: E402
from models import Proyecto, Usuario  # noqa: E402

app = create_app(Config)
with app.app_context():
    db.session.get(Usuario, 2).password_hash = 'x'

client = app.test_client()
with client.session_transaction() as ses:
    ses.update({'user_id': 2, 'username': 'hvargas', 'rol': 'zeno'})
with app.app_context():
    proyectos = [(p.id, p.nombre) for p in Proyecto.query.order_by(Proyecto.id).all()]

for nombre in ('SITE', 'FLM - CLARO'):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre=nombre).one().id
    with client.session_transaction() as ses:
        ses['current_proyecto_id'] = pid
        ses['current_proyecto_nombre'] = nombre
    r = client.get('/api/import/manual_template')
    cd = r.headers.get('Content-Disposition', '(sin cabecera)')
    print('%-14s status=%s  type=%s  disp=%s  bytes=%d  firma=%r  cuerpo=%r' % (
        nombre, r.status_code, r.headers.get('Content-Type'), cd, len(r.data), r.data[:4], r.data[:90]))
