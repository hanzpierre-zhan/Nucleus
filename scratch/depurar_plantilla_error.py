"""Depura la descarga de Plantilla cuando el módulo NO tiene columnas manuales."""
import os
import shutil
import sys
import tempfile
import threading

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

_tmp = tempfile.mkdtemp(prefix='nucleus_dbg_')
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
    pid = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
client.get('/switch_project/%s' % pid)
cookie = client.get_cookie('session')

from werkzeug.serving import make_server  # noqa: E402

servidor = make_server('127.0.0.1', 0, app, threaded=True)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:%d' % servidor.server_port

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    navegador = p.chromium.launch()
    contexto = navegador.new_context(viewport={'width': 1400, 'height': 800}, accept_downloads=True)
    contexto.add_cookies([{'name': 'session', 'value': cookie.value,
                           'domain': '127.0.0.1', 'path': '/'}])
    pagina = contexto.new_page()
    errores, descargas, consola = [], [], []
    pagina.on('pageerror', lambda e: errores.append(str(e)))
    pagina.on('console', lambda m: consola.append('%s: %s' % (m.type, m.text)))
    pagina.on('download', lambda d: descargas.append(d.suggested_filename))

    pagina.goto(url + '/', wait_until='domcontentloaded')
    pagina.wait_for_timeout(4000)
    pagina.click('#btn-module-settings')
    pagina.wait_for_timeout(300)
    pagina.click('#btn-top-plantilla')
    pagina.wait_for_timeout(3000)
    print('mensaje mostrado:', pagina.eval_on_selector(
        '#nucleus-dialog-message', 'e => e.innerText.trim()')
        if pagina.query_selector('#nucleus-dialog.show') else 'SIN AVISO')
    pagina.screenshot(path='scratch/preview_plantilla_aviso.png')
    print('descargas:', descargas)
    print('errores JS:', errores)
    print('consola:', consola[-4:])
    navegador.close()
servidor.shutdown()
