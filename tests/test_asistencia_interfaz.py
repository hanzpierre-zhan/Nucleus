import pytest
pw = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor


def test_controles_y_recorrido(auth_client, servidor, tmp_path):
    auth_client.post('/api/perfil-personal', json=dict(primer_nombre='Ana', segundo_nombre='',
        apellido_paterno='Pérez', apellido_materno='Rojas', fecha_nacimiento='1990-01-02'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome')
        context = browser.new_context(viewport={'width':1280, 'height':900})
        cookie = auth_client.get_cookie('session')
        context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(servidor+'/personal/asistencia', wait_until='networkidle')
            assert page.locator('.attendance-topbar').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            assert page.locator('#as-guardar i').count() == 1
            page.evaluate('''async () => {
                const {abrirMovil} = await import('/static/js/asistencia/movil.mjs?v=2');
                abrirMovil(1, async () => ({nombre:'Técnico de prueba',junior:'Junior de prueba',fecha:'2026-11-20',
                  proyecto:'FLM - CLARO',validacion:'PENDIENTE',editar:true,hora:'08:00',placa:'ABC123',
                  foto_url:'/static/img/brand-symbol.svg',latitud:-12.0464,longitud:-77.0428,precision:10,alertas:[],
                  recorrido:[{hora:'07:50',evento:'Abrió Nucleus',latitud:-12.045,longitud:-77.043,km:0},
                  {hora:'08:00',evento:'Asistencia',latitud:-12.0464,longitud:-77.0428,km:0}]}), () => {});
            }''')
            pw.expect(page.locator('.am-ventana')).to_be_visible()
            pw.expect(page.locator('.am-mapa .leaflet-tile')).not_to_have_count(0)
            assert 'tile.openstreetmap.org' in page.locator('.leaflet-tile').first.get_attribute('src')
            assert page.get_by_role('button',name='Cerrar',exact=True).evaluate('(e)=>getComputedStyle(e).borderRadius') == '50%'
            page.locator('.am-punto').first.click()
            page.screenshot(path=str(tmp_path/'asistencia-detalle.png'))
            page.set_viewport_size({'width':390,'height':844})
            assert page.locator('.am-ventana').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
            page.get_by_role('button',name='Cerrar',exact=True).click()
            pw.expect(page.locator('.am-ventana')).to_have_count(0)
            assert not errors, errors
        finally:
            browser.close()
