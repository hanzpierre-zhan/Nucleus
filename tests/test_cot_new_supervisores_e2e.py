import json

import pytest

from db import db
from models import NucleusData, Proyecto
from test_cot_new_supervisores import NOMBRES

pw = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor


def test_e2e_seleccionar_y_guardar_supervisor_integratel(app, auth_client, servidor):
    clave = 'QA-SUPERVISOR-INTEGRATEL'
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        fila = NucleusData(proyecto_id=proyecto.id, key_value=clave, data_json=json.dumps({
            'N° COTIZACION': clave, 'CLIENTE': 'INTEGRATEL', 'PROYECTO FLM': 'FLM - INTEGRATEL',
            'ESTADO COTIZACION': 'Pdt. Cotización', 'NUMERO WO': 'QA-WO', 'NOMBRE SITE': 'QA-SITE',
            'MOTIVO': 'Visita técnica',
            'ITEMS_JSON': json.dumps([{'texto': 'Visita técnica', 'cantidad': '1', 'valor_unitario': '20'}]),
        }))
        db.session.add(fila)
        db.session.commit()
        rid = fila.id
    try:
        with pw.sync_playwright() as playwright:
            navegador = playwright.chromium.launch(channel='chrome')
            contexto = navegador.new_context()
            contexto.add_cookies([{'name': 'session', 'value': auth_client.get_cookie('session').value,
                                   'domain': '127.0.0.1', 'path': '/'}])
            pagina = contexto.new_page()
            # El aviso de perfil tiene su propia prueba y no forma parte de este flujo.
            pagina.route('**/api/perfil-personal', lambda ruta: ruta.fulfill(
                json={'perfil': {'fecha_nacimiento': '1990-01-01'}, 'cumpleanos': []}))
            pagina.goto(servidor + '/cot-new/')
            fila_ui = pagina.locator('.cc-fila-solicitud').filter(has_text=clave)
            fila_ui.get_by_role('button', name='Editar cotización', exact=True).click()
            selector = pagina.locator('dialog[open] select').filter(
                has=pagina.locator('option', has_text='Selecciona el supervisor'))
            pw.expect(selector).to_be_visible()
            assert set(NOMBRES) <= set(selector.locator('option').all_text_contents())
            selector.select_option(NOMBRES[0])
            with pagina.expect_response(
                lambda r: '/api/cot-new/guardar' in r.url and r.request.method == 'POST', timeout=10000
            ) as guardado:
                pagina.get_by_role('button', name='Guardar', exact=True).click()
            assert guardado.value.ok
            navegador.close()
        with app.app_context():
            assert json.loads(db.session.get(NucleusData, rid).data_json)['SUPERVISOR'] == NOMBRES[0]
    finally:
        with app.app_context():
            db.session.delete(db.session.get(NucleusData, rid))
            db.session.commit()
