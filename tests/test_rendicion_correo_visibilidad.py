"""El correo de aprobación aparece según presupuesto, gasto y tiempo de respuesta."""
import json

import pytest

playwright_api = pytest.importorskip('playwright.sync_api')

from test_e2e_navegador import servidor  # noqa: E402
from db import db  # noqa: E402
from models import NucleusData, Proyecto  # noqa: E402

FILAS = {
    'MAIL-REF-MATERIAL': ('REFACTURABLE', 'Material'),
    'MAIL-REF-VIATICO': ('REFACTURABLE', 'VIÁTICOS'),
    'MAIL-GC-MATERIAL': ('GASTO COBRA', 'Material'),
    'MAIL-GC-VIATICO': ('GASTO COBRA', 'VIÁTICOS'),
}


@pytest.fixture()
def casos_de_correo(app):
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Rendicion').one()
        for key, (presupuesto, gasto) in FILAS.items():
            db.session.add(NucleusData(proyecto_id=proyecto.id, key_value=key, data_json=json.dumps({
                'ESTADO': 'PENDIENTE', 'Nombre del proyecto': 'Entel',
                'Tipo de presupuesto': presupuesto, 'Tipo de gasto': gasto,
                'Monto total del depósito': '100.00', 'Marca temporal': '01/10/2026 10:00:00'})))
        db.session.commit()
        pid = proyecto.id
    yield pid
    with app.app_context():
        NucleusData.query.filter(NucleusData.key_value.in_(list(FILAS))).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.lento
def test_correo_visible_segun_combinacion(app, auth_client, servidor, casos_de_correo, tmp_path):
    auth_client.get('/switch_project/%s' % casos_de_correo)
    cookie = auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(servidor + '/', wait_until='networkidle')
            page.wait_for_function("typeof rendValidar==='function'")
            wrap = page.locator('#rend-val-correo-wrap')

            def abrir(key):
                page.evaluate('(k) => rendValidar(k)', key)
                playwright_api.expect(page.locator('#rend-val-form')).to_be_visible()

            def cerrar():
                page.evaluate('rendCerrarModal()')

            def elegir(texto):
                page.locator('#rend-val-ops label').filter(has_text=texto).click()

            # REFACTURABLE + Material: pide correo solo con «Menor a 4 horas».
            abrir('MAIL-REF-MATERIAL')
            playwright_api.expect(wrap).to_be_visible()
            elegir('No aplica')
            playwright_api.expect(wrap).to_be_hidden()
            page.locator('#rend-val-form').screenshot(path=str(tmp_path / 'no-requiere-correo.png'))
            elegir('Menor a 4 horas')
            playwright_api.expect(wrap).to_be_visible()
            page.locator('#rend-val-form').screenshot(path=str(tmp_path / 'requiere-correo.png'))
            elegir('Atención Continua')
            playwright_api.expect(wrap).to_be_hidden()
            elegir('Mayor a 4 horas')
            playwright_api.expect(wrap).to_be_hidden()
            cerrar()

            # REFACTURABLE + VIÁTICOS: nunca lo pide.
            abrir('MAIL-REF-VIATICO')
            playwright_api.expect(wrap).to_be_hidden()
            elegir('Menor a 4 horas')
            playwright_api.expect(wrap).to_be_hidden()
            cerrar()

            # GASTO COBRA + Material: lo pide aunque el tiempo sea «No aplica».
            abrir('MAIL-GC-MATERIAL')
            playwright_api.expect(wrap).to_be_visible()
            elegir('No aplica')
            playwright_api.expect(wrap).to_be_visible()
            cerrar()

            # GASTO COBRA + VIÁTICOS: nunca lo pide.
            abrir('MAIL-GC-VIATICO')
            playwright_api.expect(wrap).to_be_hidden()
            elegir('Menor a 4 horas')
            playwright_api.expect(wrap).to_be_hidden()
            cerrar()

            assert not errors, errors
        finally:
            browser.close()
