# -*- coding: utf-8 -*-
"""Prueba de humo con un navegador real sobre '/'.

Fase 7 de la estrategia (docs/estrategia_testing.md §4.11): cubre el único
punto ciego que ninguna otra prueba alcanza, el JavaScript. Levanta la app en
un puerto local, abre '/' con un navegador de verdad y exige que la página
cargue sin errores de JavaScript y que la tabla se construya con los datos.

Si Playwright o su navegador no están instalados, la prueba se SALTA (no
falla): la suite sigue verde en cualquier máquina. Para ejecutarla:

    pip install -r requirements-dev.txt
    python -m playwright install chromium

La página es 100 % autohospedada (Tabulator y todo lo demás se sirven desde
/static), así que la prueba no necesita internet.
"""
import json
import threading

import pytest

playwright_api = pytest.importorskip(
    'playwright.sync_api',
    reason='requiere: pip install playwright && python -m playwright install chromium')

from db import db  # noqa: E402
from models import NucleusData, Proyecto  # noqa: E402

from werkzeug.serving import make_server  # noqa: E402


class _ServidorLocal(threading.Thread):
    """Sirve la app de pruebas en un hilo, en un puerto libre."""

    def __init__(self, app):
        super().__init__(daemon=True)
        self._servidor = make_server('127.0.0.1', 0, app, threaded=True)
        self.puerto = self._servidor.server_port

    def run(self):
        self._servidor.serve_forever()

    def detener(self):
        self._servidor.shutdown()
        self.join(timeout=10)


@pytest.fixture()
def servidor(app):
    servidor = _ServidorLocal(app)
    servidor.start()
    try:
        yield 'http://127.0.0.1:%d' % servidor.puerto
    finally:
        servidor.detener()


@pytest.mark.lento
def test_smoke_navegador_la_tabla_se_construye(app, auth_client, servidor):
    with app.app_context():
        proyecto = Proyecto(nombre='QA-NAVEGADOR')
        db.session.add(proyecto)
        db.session.flush()
        pid = proyecto.id
        for clave in ('N-1', 'N-2'):
            db.session.add(NucleusData(
                proyecto_id=pid, key_value=clave,
                data_json=json.dumps({'Número de WO': clave})))
        db.session.commit()
    try:
        # Sesión válida sin depender del formulario de login: se reutiliza la
        # cookie firmada que ya obtuvo el cliente de pruebas.
        auth_client.get('/switch_project/%s' % pid)
        cookie = auth_client.get_cookie('session')
        assert cookie is not None, 'no se obtuvo la cookie de sesión'

        with playwright_api.sync_playwright() as playwright:
            try:
                navegador = playwright.chromium.launch()
            except Exception as error:  # navegador no descargado
                pytest.skip('navegador de Playwright no instalado: %s' % error)
            try:
                contexto = navegador.new_context()
                contexto.add_cookies([{
                    'name': 'session', 'value': cookie.value,
                    'domain': '127.0.0.1', 'path': '/'}])
                pagina = contexto.new_page()
                errores = []
                pagina.on('pageerror', lambda error: errores.append(str(error)))

                pagina.goto(servidor + '/', wait_until='domcontentloaded')

                # La tabla la construye Tabulator dentro del navegador. Cuando
                # termina, el contador de registros queda como "visibles/total".
                playwright_api.expect(
                    pagina.locator('#status-record-count .record-count-total')
                ).to_have_text('2', timeout=20000)

                assert errores == [], 'errores de JavaScript en la página: %s' % errores
                contexto.close()
            finally:
                navegador.close()
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid).delete()
            Proyecto.query.filter_by(id=pid).delete()
            db.session.commit()
