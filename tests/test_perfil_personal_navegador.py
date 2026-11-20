import pytest
pw = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import DatosPersonalesUsuario
from services.perfil_personal import hoy_lima


def test_completar_y_editar_usuario(app, auth_client, servidor, tmp_path):
    with auth_client.session_transaction() as ses:
        uid = ses['user_id']
    with app.app_context():
        DatosPersonalesUsuario.query.filter_by(usuario_id=uid).delete()
        db.session.commit()
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome')
        context = browser.new_context(viewport={'width':1280,'height':900})
        cookie = auth_client.get_cookie('session')
        context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(servidor+'/cumpleanos', wait_until='networkidle')
            pw.expect(page.locator('.perfil-dialog')).to_be_visible()
            page.locator('[name=primer_nombre]').fill('Ana')
            page.locator('[name=apellido_paterno]').fill('Pérez')
            page.locator('[name=apellido_materno]').fill('Rojas')
            hoy = hoy_lima()
            page.locator('[name=fecha_nacimiento]').fill(f'2000-{hoy.month:02}-{hoy.day:02}')
            page.screenshot(path=str(tmp_path/'perfil-personal.png'))
            page.locator('.perfil-guardar').click()
            pw.expect(page.locator('.perfil-dialog')).to_have_count(0)
            pw.expect(page.locator('.cumple-aviso')).to_be_visible()
            pw.expect(page.locator('.cumple-aviso p')).to_contain_text('ANA PÉREZ ROJAS')
            page.locator('.cumple-cerrar').click()
            page.goto(servidor+'/cumpleanos', wait_until='networkidle')
            pw.expect(page.locator('#cumple-mes')).to_have_value(str(hoy.month))
            pw.expect(page.locator('.cumple-tabla strong')).to_contain_text('ANA PÉREZ ROJAS')
            assert page.locator('.cumple-scroll').evaluate('(e)=>getComputedStyle(e).overflowY') == 'auto'
            page.locator('#cumple-mes').select_option(str(hoy.month % 12 + 1))
            pw.expect(page.locator('.cumple-tabla tr[data-mes]:visible')).to_have_count(0)
            page.locator('#cumple-mes').select_option(str(hoy.month))
            page.screenshot(path=str(tmp_path/'cumpleanos-mes.png'))
            page.goto(servidor+'/vista/usuarios/', wait_until='networkidle')
            pw.expect(page.locator('.cumple-aviso')).to_have_count(0)
            page.locator('#vn-nuevo').click()
            pw.expect(page.get_by_text('Primer nombre', exact=True)).to_be_visible()
            pw.expect(page.locator('#cc-solicitud-contenido input[type=date]')).to_be_visible()
            assert not errors, errors
            page.screenshot(path=str(tmp_path/'usuario-datos.png'))
        finally:
            browser.close()
