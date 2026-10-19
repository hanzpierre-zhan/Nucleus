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
from models import AppConfig, LiquidacionNumero, NucleusData, Proyecto, RefacturableDetalle  # noqa: E402

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


@pytest.mark.lento
def test_liquidaciones_tarjetas_siguen_el_filtro_y_filtran_al_clic(app, auth_client, servidor):
    """Las tarjetas de Liquidaciones suman el monto de cotización de las filas
    visibles (no el total general) y, al hacer clic, filtran la grilla."""
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        origenes = []
        for clave, estado, monto in (('QA-LIQ-A', 'QA LIQ A', '100.00'),
                                     ('QA-LIQ-B', 'QA LIQ B', '50.50')):
            fila = NucleusData(
                proyecto_id=proyecto.id, key_value=clave,
                data_json=json.dumps({'N° COTIZACION': clave,
                                      'ESTADO COTIZACION': estado,
                                      'SUB TOTAL + FEE': monto,
                                      **({'ADJUNTO CORREO CLIENTE':
                                              '/api/cotizacion/correo/8/QA-LIQ-A/correo_aprob_xyz.msg?v=1',
                                          'NOMBRE CORREO CLIENTE': 'RE Aprobacion QA.msg'}
                                         if clave == 'QA-LIQ-A' else {})}))
            db.session.add(fila)
            origenes.append(fila)
        db.session.commit()
        origen_ids = [fila.id for fila in origenes]
    try:
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

                pagina.goto(servidor + '/liquidaciones/', wait_until='domcontentloaded')
                pagina.wait_for_selector('#ref-cards .ref-card', timeout=20000)

                # Columna con el nombre del archivo del correo.
                playwright_api.expect(
                    pagina.locator('.tabulator-col[tabulator-field="nombre_correo"] .ref-column-title')
                ).to_have_text('ARCHIVO DEL CORREO')
                playwright_api.expect(
                    pagina.locator('.tabulator-row', has_text='QA LIQ A').locator('.ref-file-name')
                ).to_have_text('RE Aprobacion QA.msg')

                titulos = pagina.locator('#ref-cards .ref-card-title')

                # Cada tarjeta suma el monto de cotización (SUB TOTAL + FEE).
                tarjeta_a = pagina.locator('#ref-cards .ref-card', has_text='QA LIQ A')
                playwright_api.expect(tarjeta_a.locator('.ref-card-money')).to_have_text('S/ 100.00')

                # Al escribir en el filtro, las tarjetas se recalculan con lo visible.
                filtro = pagina.locator('.tabulator-col[tabulator-field="estado_cotizacion"] input')
                filtro.click()
                filtro.press_sequentially('QA LIQ A', delay=20)
                playwright_api.expect(titulos).to_have_text(['QA LIQ A', 'Total'])
                playwright_api.expect(
                    pagina.locator('#ref-cards .ref-card.is-total .ref-card-count')
                ).to_have_text('1 caso')

                # Clic en "Total" limpia el filtro de estado.
                pagina.locator('#ref-cards .ref-card', has_text='Total').click()
                playwright_api.expect(filtro).to_have_value('')
                playwright_api.expect(titulos).to_have_text(['QA LIQ A', 'QA LIQ B', 'Total'])

                # Clic en una tarjeta filtra la grilla por ese estado.
                pagina.locator('#ref-cards .ref-card', has_text='QA LIQ B').click()
                playwright_api.expect(filtro).to_have_value('QA LIQ B')
                playwright_api.expect(titulos).to_have_text(['QA LIQ B', 'Total'])

                assert errores == [], 'errores de JavaScript en la página: %s' % errores
                contexto.close()
            finally:
                navegador.close()
    finally:
        with app.app_context():
            RefacturableDetalle.query.filter(
                RefacturableDetalle.origen_id.in_(origen_ids)
            ).delete(synchronize_session=False)
            LiquidacionNumero.query.filter(
                LiquidacionNumero.origen_id.in_(origen_ids)
            ).delete(synchronize_session=False)
            NucleusData.query.filter(NucleusData.id.in_(origen_ids)).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.lento
def test_plantilla_manual_avisa_el_error_en_vez_de_bajar_json(app, auth_client, servidor):
    """El botón "Plantilla" del módulo nunca guarda un .json de error a escondidas:
    si el proyecto no tiene columnas manuales, muestra el motivo en pantalla; y
    cuando sí las tiene, descarga el .xlsx con su nombre."""
    with app.app_context():
        proyecto = Proyecto(nombre='QA-PLANTILLA')
        db.session.add(proyecto)
        db.session.flush()
        pid = proyecto.id
        db.session.commit()
    try:
        auth_client.get('/switch_project/%s' % pid)
        cookie = auth_client.get_cookie('session')
        assert cookie is not None, 'no se obtuvo la cookie de sesión'

        with playwright_api.sync_playwright() as playwright:
            try:
                navegador = playwright.chromium.launch()
            except Exception as error:  # navegador no descargado
                pytest.skip('navegador de Playwright no instalado: %s' % error)
            try:
                contexto = navegador.new_context(accept_downloads=True)
                contexto.add_cookies([{
                    'name': 'session', 'value': cookie.value,
                    'domain': '127.0.0.1', 'path': '/'}])
                pagina = contexto.new_page()
                errores = []
                pagina.on('pageerror', lambda error: errores.append(str(error)))
                descargas = []
                pagina.on('download', lambda descarga: descargas.append(descarga.suggested_filename))

                pagina.goto(servidor + '/', wait_until='domcontentloaded')
                pagina.wait_for_selector('#btn-module-settings', timeout=20000)

                # Sin columnas manuales: aviso en pantalla, sin archivo .json.
                pagina.click('#btn-module-settings')
                pagina.click('#btn-top-plantilla')
                # El aviso nativo se muestra con el popup temático de la app.
                playwright_api.expect(
                    pagina.locator('#nucleus-dialog-message')
                ).to_contain_text('columnas manuales', timeout=20000)
                assert descargas == [], 'descargó %s en vez de avisar' % descargas
                pagina.click('#nucleus-dialog-ok')

                # Con columnas manuales: baja el Excel de verdad.
                with app.app_context():
                    db.session.add(AppConfig(proyecto_id=pid, clave='manual_columns',
                                             valor=json.dumps([{'nombre': 'COMENTARIOS'}])))
                    db.session.commit()
                pagina.reload(wait_until='domcontentloaded')
                pagina.wait_for_selector('#btn-module-settings', timeout=20000)
                pagina.click('#btn-module-settings')
                with pagina.expect_download() as informacion:
                    pagina.click('#btn-top-plantilla')
                assert informacion.value.suggested_filename == 'plantilla_columnas_manuales.xlsx'

                assert errores == [], 'errores de JavaScript en la página: %s' % errores
                contexto.close()
            finally:
                navegador.close()
    finally:
        with app.app_context():
            AppConfig.query.filter_by(proyecto_id=pid).delete()
            Proyecto.query.filter_by(id=pid).delete()
            db.session.commit()
