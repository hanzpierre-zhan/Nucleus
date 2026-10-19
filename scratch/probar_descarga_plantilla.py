"""Prueba real de descarga: ¿la plantilla de SITE baja como .xlsx o como .json?"""
import os
import shutil
import sys
import tempfile
import threading

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

_tmp = tempfile.mkdtemp(prefix='nucleus_dl_')
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
    pid_site = Proyecto.query.filter_by(nombre='SITE').one().id
client.get('/switch_project/%s' % pid_site)
cookie = client.get_cookie('session')

from werkzeug.serving import make_server  # noqa: E402

servidor = make_server('127.0.0.1', 0, app, threaded=True)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:%d' % servidor.server_port

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    navegador = p.chromium.launch()
    contexto = navegador.new_context(viewport={'width': 1680, 'height': 900}, accept_downloads=True)
    contexto.add_cookies([{'name': 'session', 'value': cookie.value,
                           'domain': '127.0.0.1', 'path': '/'}])
    pagina = contexto.new_page()
    respuestas = []
    pagina.on('response', lambda r: respuestas.append(r) if 'manual_template' in r.url else None)

    pagina.goto(url + '/', wait_until='domcontentloaded')
    pagina.wait_for_timeout(4000)

    # Abrir el engranaje (Configuración) para llegar al botón Plantilla.
    pagina.click('#btn-module-settings')
    pagina.wait_for_timeout(500)
    visibles = pagina.eval_on_selector(
        '#module-settings-menu', "e => [...e.querySelectorAll('a,button')].map(x => (x.innerText||'').trim())")
    print('menu Configuración:', visibles)

    with pagina.expect_download() as info:
        pagina.click('#btn-top-plantilla')
    descarga = info.value
    print('nombre sugerido:', descarga.suggested_filename)
    for r in respuestas:
        print('respuesta:', r.status, r.headers.get('content-type'),
              '| disposition:', r.headers.get('content-disposition'))
    ruta = os.path.join(_tmp, 'descargado')
    descarga.save_as(ruta)
    with open(ruta, 'rb') as fh:
        print('firma del archivo:', fh.read(4), '| bytes:', os.path.getsize(ruta))
    navegador.close()
servidor.shutdown()
