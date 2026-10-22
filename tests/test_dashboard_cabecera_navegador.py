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
            for path in ['/analytics','/analytics/cotizaciones','/analytics/rendicion','/analytics/cobranza']:
                page.goto(servidor+path,wait_until='networkidle')
                assert page.locator('.dashboard-header').count()==1
                assert page.locator('.dashboard-header>.dash-switch').count()==1
                assert page.locator('.dashboard-header .di-eyebrow,.dashboard-header .re-key').count()==0
                positions.append(page.locator('.dash-switch').bounding_box())
                assert page.locator('.di-page').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            assert max(pos['x'] for pos in positions)-min(pos['x'] for pos in positions)<1
            assert max(pos['y'] for pos in positions)-min(pos['y'] for pos in positions)<1
            assert not errors,errors
        finally:
            browser.close()
