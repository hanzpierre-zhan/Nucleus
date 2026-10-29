"""El layout guardado no puede dejar Validación sin botones del flujo."""
import json
import pytest
from db import db
from models import Proyecto,AppConfig,NucleusData
from test_e2e_navegador import servidor
pw=pytest.importorskip('playwright.sync_api')


def test_flujo_visible_con_layout_que_lo_ocultaba(app,auth_client,servidor):
    previous={}
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        for key,layout in [('column_layout',[{'field':'ESTADO','visible':True}]),('column_layout__validacion',[{'field':'ESTADO','visible':True},{'field':'_accion','visible':False}])]:
            cfg=AppConfig.query.filter_by(proyecto_id=pid,clave=key).first()
            previous[key]=cfg.valor if cfg else None
            if not cfg:cfg=AppConfig(proyecto_id=pid,clave=key);db.session.add(cfg)
            cfg.valor=json.dumps(layout)
        db.session.add(NucleusData(proyecto_id=pid,key_value='FLUJO-REGRESION',data_json=json.dumps({'ESTADO':'PENDIENTE','Nombre del proyecto':'Claro'})))
        db.session.commit()
    try:
        auth_client.get('/switch_project/'+str(pid));cookie=auth_client.get_cookie('session')
        with pw.sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                context=browser.new_context(viewport={'width':1500,'height':900})
                context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
                page=context.new_page();page.goto(servidor+'/',wait_until='networkidle')
                page.wait_for_function("typeof _rendFiltroFn==='function'")
                for action in ['initial','switch','reload']:
                    if action=='switch':page.evaluate("rendCambiarVista('depositos');rendCambiarVista('validacion')")
                    if action=='reload':page.reload(wait_until='networkidle')
                    page.wait_for_function("table.getColumn('_accion').isVisible()")
                    pw.expect(page.locator('.tabulator-col[tabulator-field="_accion"]')).to_be_visible()
                    assert page.locator('.tabulator-row [tabulator-field="_accion"] button').count()>0
            finally:browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid,key_value='FLUJO-REGRESION').delete()
            for key,value in previous.items():
                cfg=AppConfig.query.filter_by(proyecto_id=pid,clave=key).one()
                if value is None:db.session.delete(cfg)
                else:cfg.valor=value
            db.session.commit()
