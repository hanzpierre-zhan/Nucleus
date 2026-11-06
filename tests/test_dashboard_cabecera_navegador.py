import pytest
playwright_api=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor


def test_cabeceras_comparten_orden_y_posicion(app,auth_client,servidor):
    cookie=auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            context=browser.new_context(viewport={'width':1352,'height':900})
            context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
            page=context.new_page();errors=[];positions=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            for path in ['/analytics/entel','/analytics/claro','/analytics/integratel','/analytics/pext',
                         '/analytics/cotizaciones','/analytics/rendicion','/analytics/gerencial']:
                page.goto(servidor+path,wait_until='networkidle')
                assert page.locator('.dashboard-header').count()==1
                assert page.locator('.dashboard-switch-bar > .dash-switch').count()==1
                assert page.locator('.dashboard-switch-bar + .dashboard-header').count()==1
                assert page.locator('.dash-switch [aria-current="page"]').count()==1
                assert page.locator('.dash-switch [aria-current="page"]').get_attribute('href')==path
                assert page.evaluate("""() => getComputedStyle(document.querySelector('.dash-switch .is-active')).backgroundColor
                    === getComputedStyle(document.querySelector('.sidebar-link[data-nav="/analytics"]')).backgroundColor""")
                assert page.locator('.dash-switch a').count()==7
                assert page.locator('.dash-switch a[href="/analytics/cobranza"]').count()==0
                assert page.locator('.dash-switch-label').count()==0
                if path in ('/analytics/entel','/analytics/integratel','/analytics/pext'):
                    assert page.locator('.di-story').count()==0
                if path == '/analytics/claro':
                    assert page.locator('#cl-exportar').count()==0
                    assert page.locator('[data-cl-scale]').all_text_contents()==['Diario','Semanal','Mensual','Trimestre','Anual']
                    page.get_by_role('button', name='Trimestre').click()
                    assert page.locator('[data-cl-scale="trimestre"]').get_attribute('aria-pressed')=='true'
                    assert page.locator('#cl-excluir-cancelados').is_checked()
                assert page.locator('.dashboard-header .di-eyebrow,.dashboard-header .re-key').count()==0
                positions.append(page.locator('.dash-switch').bounding_box())
                assert page.locator('.di-page').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            assert max(pos['x'] for pos in positions)-min(pos['x'] for pos in positions)<1
            assert max(pos['y'] for pos in positions)-min(pos['y'] for pos in positions)<1
            assert not errors,errors
        finally:
            browser.close()
