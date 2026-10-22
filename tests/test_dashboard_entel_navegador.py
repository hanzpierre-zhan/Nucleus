"""Carga real del dashboard Entel al entrar desde otro proyecto."""
import json
import pytest
playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import Proyecto, NucleusData


def test_entel_dibuja_datos_desde_otro_modulo(app, auth_client, servidor, tmp_path):
    with app.app_context():
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        otro = Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        fila = NucleusData(proyecto_id=entel, key_value='ENTEL-BROWSER', data_json=json.dumps({
            'Operate Phase':'close', 'FECHA DE CREACION':'2026-10-01',
            'Departamento':'LIMA', 'Nombre de Site':'SITE ENTEL QA', 'Tipo tarea':'ENERGIA'
        }))
        db.session.add(fila); db.session.commit(); fid=fila.id
        extra_ids=[]
        for n in range(60):
            extra=NucleusData(proyecto_id=entel,key_value='ENTEL-VISUAL-'+str(n),data_json=json.dumps({
                'Operate Phase':'close' if n%4 else 'dispatch','FECHA DE CREACION':f'2026-{7+n%4:02d}-{1+n%20:02d}',
                'Departamento':['LIMA','JUNIN','ICA'][n%3], 'Nombre de Site':'SITE '+str(n%10),
                'Tipo tarea':['ENERGIA','MANTENIMIENTO','RADIO'][n%3],
                'Nombre de personal FLM asignado':'TECNICO '+str(n%5), 'Prioridad del Site':['P1','P2','P3'][n%3],
                'Fault Level':['Alta','Media','Baja'][n%3]
            }))
            db.session.add(extra);db.session.flush();extra_ids.append(extra.id)
        db.session.commit()
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
                playwright_api.expect(page.locator('#di-sites')).to_contain_text('SITE 1')
                assert int(page.locator('#di-production').inner_text()) >= 1
                assert page.locator('#di-daily svg').count() == 1
                assert page.locator('#di-months .di-month').count() >= 1
                assert page.locator('#di-priority canvas,#di-fault canvas').count() == 2
                for dark in (False,True):
                    page.evaluate('(dark)=>document.body.classList.toggle("dark-mode",dark)',dark)
                    for width in (1352,390):
                        page.set_viewport_size({'width':width,'height':900})
                        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                        page.screenshot(path=str(tmp_path/f'entel-{dark}-{width}.png'),full_page=True,animations='disabled')
                        assert page.locator('.di-page').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                assert not errors, errors
            finally:
                browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_([fid]+extra_ids)).delete(synchronize_session=False); db.session.commit()
