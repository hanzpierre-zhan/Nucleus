"""Carga y validación del correo desde la interfaz, con datos aislados."""
import pytest
playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from test_rendicion_correo import solicitud


def test_adjuntar_correo_y_validar_sin_volver_a_pedirlo(app, auth_client, servidor, solicitud, monkeypatch, tmp_path):
    import blueprints.rendicion as rend
    monkeypatch.setattr(rend, '_correo_folder', lambda rid: str(tmp_path / str(rid)))
    cookie = auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1352, 'height': 900})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(servidor + '/', wait_until='networkidle')
            page.wait_for_function("typeof rawData !== 'undefined' && rawData.some(r=>r._key==='REND-CORREO-TEST')")
            page.evaluate("rendValidar('REND-CORREO-TEST')")
            page.locator('#rend-val-correo').set_input_files({'name': 'aprobacion.msg', 'mimeType': 'application/vnd.ms-outlook', 'buffer': b'correo de prueba'})
            playwright_api.expect(page.locator('#rend-val-correo-status')).to_contain_text('Correo adjunto:')
            page.locator('#rend-val-ops label').filter(has_text='No aplica').click()
            # Simula el cambio de servidor o reinicio que elimina el disco efímero.
            for archivo in tmp_path.rglob('*.msg'):
                archivo.unlink()
            with page.expect_response(lambda r: '/api/rendicion/accion' in r.url and r.request.method == 'POST') as response:
                page.locator('#rend-modal-ok').click()
            assert response.value.status == 200, response.value.text()
            assert response.value.json()['newData']['ESTADO'] == 'VALIDADO'
            assert not errors, errors
        finally:
            browser.close()
