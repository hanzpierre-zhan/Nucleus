import json
import pytest
playwright_api=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import Proyecto,AppConfig


def test_ancho_flujo_se_conserva_por_pestana_y_recarga(app,auth_client,servidor):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    auth_client.get(f'/switch_project/{pid}')
    for vista,width in [('sustentar',64),('atendido',184)]:
        response=auth_client.post('/api/columns/layout',json={'vista':'flujo_'+vista,'columns':[{'field':'_accion_cot','width':width,'visible':True}]})
        assert response.status_code==200
    auth_client.get('/')
    with app.app_context():
        config=AppConfig.query.filter_by(proyecto_id=pid,clave='column_layout').first()
        original=config.valor if config else None
    cookie=auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            context=browser.new_context()
            context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(servidor+'/',wait_until='networkidle')
            page.wait_for_function('typeof table!=="undefined" && table.getColumn("_accion_cot")')
            for vista,width in [('sustentar',64),('atendido',184),('sustentar',64)]:
                page.evaluate('(vista)=>cotCambiarVista(vista)',vista)
                assert page.evaluate('()=>table.getColumn("_accion_cot").getWidth()')==width
            page.evaluate('async()=>{table.getColumn("_accion_cot").setWidth(78);await cotGuardarAnchoFlujo(78);}')
            page.evaluate('()=>cotCambiarVista("atendido")')
            assert page.evaluate('()=>table.getColumn("_accion_cot").getWidth()')==184
            page.reload(wait_until='networkidle')
            page.wait_for_function('typeof table!=="undefined" && table.getColumn("_accion_cot")')
            page.evaluate('()=>cotCambiarVista("sustentar")')
            assert page.evaluate('()=>table.getColumn("_accion_cot").getWidth()')==78
            assert not errors,errors
        finally:
            browser.close()
    with app.app_context():
        config=AppConfig.query.filter_by(proyecto_id=pid,clave='column_layout').first()
        assert (config.valor if config else None)==original
