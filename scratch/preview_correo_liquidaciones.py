"""Captura de la columna ARCHIVO DEL CORREO con datos reales.

Usa una COPIA de nucleus.db (no toca la base original): a la copia se le pone
una clave conocida al usuario 2 solo para poder entrar y tomar la captura.
"""
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
from models import Usuario  # noqa: E402

app = create_app(Config)
with app.app_context():
    usuario = db.session.get(Usuario, 2)
    usuario.password_hash = generate_password_hash('preview123')
    db.session.commit()

client = app.test_client()
r = client.post('/login', data={'username': 'hvargas', 'password': 'preview123', 'legal_accept': '1'})
if r.status_code == 200 and b'name="consent_step"' in r.data:
    r = client.post('/login', data={'consent_step': '1', 'legal_accept': '1'})
assert r.status_code in (301, 302), 'login de vista previa falló: %s %s' % (r.status_code, r.data[:200])
cookie = client.get_cookie('session')

from werkzeug.serving import make_server  # noqa: E402

servidor = make_server('127.0.0.1', 0, app, threaded=True)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:%d' % servidor.server_port

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    navegador = p.chromium.launch()
    contexto = navegador.new_context(viewport={'width': 1680, 'height': 900})
    contexto.add_cookies([{'name': 'session', 'value': cookie.value,
                           'domain': '127.0.0.1', 'path': '/'}])
    pagina = contexto.new_page()
    errores = []
    pagina.on('pageerror', lambda e: errores.append(str(e)))
    pagina.goto(url + '/liquidaciones/', wait_until='domcontentloaded')
    pagina.wait_for_selector('#ref-grid .tabulator-row', timeout=30000)
    pagina.wait_for_timeout(1500)

    # Filtrar por la columna nueva para dejar a la vista solo filas con nombre.
    filtro = pagina.locator('.tabulator-col[tabulator-field="nombre_correo"] input')
    filtro.click()
    filtro.press_sequentially('correo_aprob', delay=15)
    pagina.wait_for_timeout(1200)

    # Desplazar la grilla hasta la columna nueva.
    pagina.evaluate("""() => {
        const holder = document.querySelector('#ref-grid .tabulator-tableholder');
        const col = document.querySelector('.tabulator-col[tabulator-field="nombre_correo"]');
        if (holder && col) holder.scrollLeft = col.offsetLeft - 220;
    }""")
    pagina.wait_for_timeout(600)

    print('filas visibles:', pagina.locator('#ref-grid .tabulator-row').count())
    print('badge:', pagina.locator('#ref-count').inner_text())
    print('nombres:', pagina.locator('#ref-grid .ref-file-name').all_inner_texts()[:5])
    pagina.screenshot(path=os.path.join('scratch', 'preview_correo_liquidaciones.png'))
    print('errores JS:', errores)
    navegador.close()
servidor.shutdown()
