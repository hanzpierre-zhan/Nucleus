"""Carga real del dashboard Entel al entrar desde otro proyecto."""
import json
import pytest
playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import Proyecto, NucleusData


def test_entel_dibuja_datos_desde_otro_modulo(app, auth_client, servidor):
    with app.app_context():
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        otro = Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        fila = NucleusData(proyecto_id=entel, key_value='ENTEL-BROWSER', data_json=json.dumps({
            'Operate Phase':'close', 'FECHA DE CREACION':'2026-10-01',
            'Departamento':'LIMA', 'Nombre de Site':'SITE ENTEL QA', 'Tipo tarea':'ENERGIA'
        }))
        db.session.add(fila); db.session.commit(); fid=fila.id
    try:
        auth_client.get(f'/switch_project/{otro}')
        cookie = auth_client.get_cookie('session')
        with playwright_api.sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                context=browser.new_context()
                context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
                page=context.new_page(); errors=[]
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(servidor+'/analytics',wait_until='networkidle')
                playwright_api.expect(page.locator('#di-sites')).to_contain_text('SITE ENTEL QA')
                assert int(page.locator('#di-production').inner_text()) >= 1
                assert page.locator('#di-daily svg').count() == 1
                assert page.locator('#di-months .di-month').count() >= 1
                assert not errors, errors
            finally:
                browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=fid).delete(); db.session.commit()
