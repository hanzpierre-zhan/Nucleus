"""Vista previa de Combustible + Generadores (sobre una COPIA de nucleus.db)."""
import os
import shutil
import sys
import tempfile
import threading

from werkzeug.security import generate_password_hash

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

_tmp = tempfile.mkdtemp(prefix='nucleus_preview_')
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
    db.session.get(Usuario, 2).password_hash = generate_password_hash('preview123')
    db.session.commit()
    pid_comb = Proyecto.query.filter_by(nombre='Combustible').one().id
    pid_gen = Proyecto.query.filter_by(nombre='Generadores').one().id

client = app.test_client()
r = client.post('/login', data={'username': 'hvargas', 'password': 'preview123', 'legal_accept': '1'})
if r.status_code == 200 and b'name="consent_step"' in r.data:
    r = client.post('/login', data={'consent_step': '1', 'legal_accept': '1'})
assert r.status_code in (301, 302), 'login de vista previa falló: %s' % r.status_code
client.get('/switch_project/%s' % pid_comb)
cookie = client.get_cookie('session')

from werkzeug.serving import make_server  # noqa: E402

servidor = make_server('127.0.0.1', 0, app, threaded=True)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:%d' % servidor.server_port

from playwright.sync_api import sync_playwright  # noqa: E402

TOOLBAR = "e => [...e.querySelectorAll('.action-pill')].map(x => (x.innerText || '').trim()).filter(Boolean)"
MENU = "e => [...e.querySelectorAll('.sidebar-link-text')].map(x => x.textContent.trim())"

with sync_playwright() as p:
    navegador = p.chromium.launch()
    contexto = navegador.new_context(viewport={'width': 1680, 'height': 900})
    contexto.add_cookies([{'name': 'session', 'value': cookie.value,
                           'domain': '127.0.0.1', 'path': '/'}])
    pagina = contexto.new_page()
    errores = []
    pagina.on('pageerror', lambda e: errores.append(str(e)))

    pagina.goto(url + '/', wait_until='domcontentloaded')
    pagina.wait_for_timeout(4000)
    print('sidebar (Combustible):', pagina.eval_on_selector('.sidebar-nav', MENU))
    print('barra (Combustible):', pagina.eval_on_selector('.topbar-row', TOOLBAR))
    print('titulo activo:', pagina.eval_on_selector('.sidebar-link.active', "e => e.innerText.trim()"))
    pagina.screenshot(path='scratch/preview_combustible.png')

    pagina.click('a.action-pill[href="/switch_project/%s?next=/"]' % pid_gen)
    pagina.wait_for_timeout(5000)
    print('sidebar (Generadores):', pagina.eval_on_selector('.sidebar-nav', MENU))
    print('barra (Generadores):', pagina.eval_on_selector('.topbar-row', TOOLBAR))
    print('titulo activo:', pagina.eval_on_selector('.sidebar-link.active', "e => e.innerText.trim()"))
    pagina.screenshot(path='scratch/preview_generadores.png')

    print('errores JS:', errores)
    navegador.close()
servidor.shutdown()
