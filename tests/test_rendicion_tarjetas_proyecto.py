"""Las tarjetas de resumen de Rendición se recalculan por proyecto."""
import json

import pytest

playwright_api = pytest.importorskip('playwright.sync_api')

from test_e2e_navegador import servidor  # noqa: E402
from db import db  # noqa: E402
from models import NucleusData, Proyecto  # noqa: E402

FILAS = [
    ('REND-PROY-ENTEL-1', 'Entel', 'VALIDADO', '100.50'),
    ('REND-PROY-ENTEL-2', 'Entel', 'DEPOSITADO', '200'),
    ('REND-PROY-CLARO-1', 'Claro', 'VALIDADO', '50'),
    ('REND-PROY-INTEGRATEL-1', 'Integratel', 'VALIDADO', '25'),
]

# Calcula el valor esperado con los datos que la propia página cargó, para que
# la prueba no dependa de filas que hayan dejado otros tests en Rendición.
ESPERADO_JS = """([proyecto, estado]) => {
    let monto = 0, casos = 0;
    rawData.forEach(r => {
        if (proyecto && rendProyectoDe(r) !== proyecto) return;
        if (rendEstadoParaVista(r) !== estado) return;
        monto += rendMontoFila(r);
        casos += 1;
    });
    return [monto, casos];
}"""


@pytest.fixture()
def rendicion_con_proyectos(app):
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Rendicion').one()
        for key, nombre, estado, monto in FILAS:
            db.session.add(NucleusData(proyecto_id=proyecto.id, key_value=key, data_json=json.dumps({
                'Nombre del proyecto': nombre, 'ESTADO': estado, 'MONTO PAGO': monto,
                'Número CM / PM / PLM': key, 'Marca temporal': '01/10/2026 10:00:00'})))
        db.session.commit()
        pid = proyecto.id
    yield pid
    with app.app_context():
        NucleusData.query.filter(NucleusData.key_value.in_([f[0] for f in FILAS])).delete(synchronize_session=False)
        db.session.commit()


def _esperado(page, proyecto, estado):
    monto, casos = page.evaluate(ESPERADO_JS, [proyecto, estado])
    return f'S/ {monto:,.2f}', str(casos)


@pytest.mark.lento
def test_tarjetas_por_proyecto_en_rendicion(app, auth_client, servidor, rendicion_con_proyectos, tmp_path):
    auth_client.get('/switch_project/%s' % rendicion_con_proyectos)
    cookie = auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1600, 'height': 1000})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(servidor + '/', wait_until='networkidle')

            selector = page.locator('#rend-proyecto')
            playwright_api.expect(selector).to_be_visible()
            etiquetas = selector.locator('option').all_text_contents()
            assert etiquetas[0] == 'Todos los proyectos'
            for nombre in ('FLM - ENTEL', 'FLM - CLARO', 'FLM - INTEGRATEL'):
                total = page.evaluate("nombre => rawData.filter(r => rendProyectoDe(r) === nombre).length", nombre)
                assert nombre + ' · ' + str(total) in etiquetas, etiquetas

            monto_depositos = page.locator('[data-rend-monto="depositos"]')
            casos_depositos = page.locator('[data-rend-cnt="depositos"]')
            todos = _esperado(page, '', 'VALIDADO')
            playwright_api.expect(monto_depositos).to_have_text(todos[0])
            playwright_api.expect(casos_depositos).to_have_text(todos[1])

            selector.select_option('FLM - ENTEL')
            entel = _esperado(page, 'FLM - ENTEL', 'VALIDADO')
            assert entel[0] != todos[0], 'el filtro de proyecto no cambió las tarjetas'
            playwright_api.expect(monto_depositos).to_have_text(entel[0])
            playwright_api.expect(casos_depositos).to_have_text(entel[1])
            evidencia = _esperado(page, 'FLM - ENTEL', 'DEPOSITADO')
            playwright_api.expect(page.locator('[data-rend-monto="evidencia"]')).to_have_text(evidencia[0])
            playwright_api.expect(page.locator('[data-rend-cnt="evidencia"]')).to_have_text(evidencia[1])
            page.screenshot(path=str(tmp_path / 'rendicion-tarjetas-entel.png'),
                            clip={'x': 0, 'y': 0, 'width': 1600, 'height': 340})

            selector.select_option('FLM - CLARO')
            claro = _esperado(page, 'FLM - CLARO', 'VALIDADO')
            playwright_api.expect(monto_depositos).to_have_text(claro[0])
            playwright_api.expect(casos_depositos).to_have_text(claro[1])

            # La elección sobrevive a una recarga de la página.
            selector.select_option('FLM - INTEGRATEL')
            page.reload(wait_until='networkidle')
            playwright_api.expect(page.locator('#rend-proyecto')).to_have_value('FLM - INTEGRATEL')
            integratel = _esperado(page, 'FLM - INTEGRATEL', 'VALIDADO')
            playwright_api.expect(page.locator('[data-rend-monto="depositos"]')).to_have_text(integratel[0])

            page.locator('#rend-proyecto').select_option('')
            playwright_api.expect(page.locator('[data-rend-monto="depositos"]')).to_have_text(todos[0])
            for ancho in (1724, 1365):
                page.set_viewport_size({'width': ancho, 'height': 900})
                assert page.locator('.rend-formularios').evaluate(
                    '(e) => e.scrollWidth <= e.clientWidth + 1'), ancho
                assert page.locator('#rend-proyecto').is_visible()
                page.screenshot(path=str(tmp_path / ('rendicion-tarjetas-' + str(ancho) + '.png')),
                                clip={'x': 0, 'y': 0, 'width': ancho, 'height': 320})
            assert not errors, errors
        finally:
            browser.close()
