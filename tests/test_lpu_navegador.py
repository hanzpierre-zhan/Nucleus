import pytest
playwright_api=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import LpuRegistro


def test_lpu_desde_liquidaciones_agrega_y_edita(app,auth_client,servidor,tmp_path):
    cookie=auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            context=browser.new_context(viewport={'width':1500,'height':950})
            context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(servidor+'/liquidaciones/',wait_until='networkidle')
            page.get_by_role('link',name='LPU',exact=True).click()
            page.wait_for_function('window.Tabulator && Tabulator.findTable("#lpu-grid")[0]?.getData().length>=214')
            page.evaluate('document.body.classList.add("dark-mode")')
            page.get_by_role('button',name='+ Agregar',exact=True).click()
            page.locator('#lpu-form [name=code]').fill('QA-LPU-UI')
            page.locator('#lpu-form [name=unit]').fill('UND')
            page.locator('#lpu-form [name=description_es]').fill('Registro de prueba desde interfaz')
            page.locator('#lpu-form [name=description_en]').fill('UI test')
            page.locator('#lpu-form [name=activity]').fill('Actividad manual')
            page.get_by_role('button',name='Guardar',exact=True).click()
            playwright_api.expect(page.locator('#lpu-dialog')).not_to_be_visible()
            page.locator('.tabulator-col[tabulator-field=code] .tabulator-header-filter input').fill('QA-LPU-UI')
            cell=page.locator('.tabulator-row .tabulator-cell[tabulator-field=unit]').first
            cell.dblclick();cell.locator('input').fill('m')
            with page.expect_response(lambda r:'/liquidaciones/api/lpu/' in r.url and r.request.method=='PATCH') as response:
                cell.locator('input').press('Enter')
            assert response.value.status==200,response.value.text()
            playwright_api.expect(page.locator('#lpu-status')).to_have_text('Cambio guardado.')
            with page.expect_download() as download:
                page.get_by_role('link',name='Descargar plantilla',exact=True).click()
            assert download.value.suggested_filename=='Plantilla_LPU.xlsx'
            page.locator('.tabulator-col[tabulator-field=code] .tabulator-header-filter input').fill('')
            page.screenshot(path=str(tmp_path/'catalogo-lpu.png'))
            assert not errors,errors
        finally:
            browser.close()
            with app.app_context():LpuRegistro.query.filter_by(code='QA-LPU-UI').delete();db.session.commit()
