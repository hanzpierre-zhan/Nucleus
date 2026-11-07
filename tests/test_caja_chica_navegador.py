import json
from playwright.sync_api import sync_playwright, expect
from test_e2e_navegador import servidor
from test_caja_chica import tecnico


def test_justificacion_en_etapas_y_editor_conserva_detalles(app, auth_client, servidor, tecnico):
    cli, headers = tecnico
    result = cli.post('/form-pruebas/caja-chica/solicitar', headers=headers, json={
        'proyecto': 'CLARO', 'motivo': 'Justificación completa\nSegunda línea', 'banco': 'BCP',
        'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50', 'descripcion': 'Detalle original'}]})
    assert result.status_code == 200, result.json
    sol = result.json['solicitud']
    auth_client.get('/caja-chica/')
    cookie = auth_client.get_cookie('session')
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1400, 'height': 1000})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            states = [('PENDIENTE', 'validacion'), ('VALIDADO', 'deposito'), ('DEPOSITADO', 'por_rendir'),
                      ('DEPOSITADO', 'revision'), ('ARCHIVADO', 'archivado'), ('ANULADO', 'anuladas')]
            for estado, etapa in states:
                data = {**sol, 'estado': estado, 'etapas': [etapa], 'revision': {}, 'envio_tecnico': None,
                        'depositado_en': '2026-11-06T12:00' if estado == 'DEPOSITADO' else ''}
                page.route('**/api/caja-chica/solicitudes', lambda route, request, data=data: route.fulfill(json={'solicitudes': [data]}))
                page.goto(servidor + '/caja-chica/')
                page.locator('[data-tab="' + etapa + '"]').click()
                page.locator('#cc-lista a').filter(has_text=sol['codigo']).click()
                expect(page.locator('.cc-justificacion')).to_be_visible()
                expect(page.locator('.cc-justificacion-texto')).to_have_text(sol['motivo'])
                if etapa == 'deposito':
                    resumen = page.locator('.cc-deposito-resumen')
                    monto = resumen.locator('.cc-deposito-cabecera').bounding_box()
                    banco = resumen.locator('.cc-ficha').bounding_box()
                    assert abs(monto['y'] - banco['y']) < 2
                    assert banco['x'] > monto['x']
                    solicitud = page.locator('.cc-deposito-solicitud')
                    expect(solicitud.locator('.cc-ficha-titulo').first).to_have_text('Datos de la solicitud')
                    assert solicitud.locator('.cc-ficha-concepto').count() == len(sol['items']) + 1
                    expect(solicitud.locator('.cc-ficha-concepto').first).to_contain_text('Peajes')
                    expect(solicitud.locator('.cc-justificacion-texto')).to_have_text(sol['motivo'])
                if estado == 'PENDIENTE':
                    page.locator('#cc-solicitud-editar').click()
                    expect(page.locator('#cc-solicitud-editor textarea')).to_have_value(sol['motivo'])
                    assert page.locator('#cc-solicitud-editor input[placeholder="Descripción"]').count() == 0
                    assert page.locator('#cc-solicitud-editor input[type="email"]').count() == 0
                    with page.expect_request('**/api/caja-chica/*/editar') as request:
                        page.locator('#cc-solicitud-guardar').click()
                    assert 'Detalle original' in request.value.post_data
                page.unroute('**/api/caja-chica/solicitudes')
            assert not errors, errors
        finally:
            browser.close()


def test_portal_tecnico_sin_contadores_y_botones_redondos(app, servidor, tecnico):
    cli, headers = tecnico
    result = cli.post('/form-pruebas/caja-chica/solicitar', headers=headers, json={
        'proyecto': 'CLARO', 'motivo': 'Solicitud activa de prueba', 'banco': 'BCP',
        'cuenta': '00123456789012345678', 'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}]})
    assert result.status_code == 200, result.json
    cookie = cli.get_cookie('session')
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 390, 'height': 844})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(servidor + '/form-pruebas/caja-chica')
            expect(page.locator('#cc-inicio')).to_be_visible()
            assert page.locator('#cc-filtros').count() == 0
            card = page.locator('#cc-lista button.deposit').filter(has_text=result.json['solicitud']['codigo'])
            expect(card).to_be_visible()
            assert card.evaluate('e=>getComputedStyle(e).borderRadius') == '24px'
            card.click()
            volver = page.locator('#cc-detalle-rendicion button[data-cc-volver]')
            expect(volver).to_be_visible()
            assert volver.evaluate('e=>getComputedStyle(e).borderRadius') == '999px'
            volver.click()
            expect(card).to_be_visible()
            assert not errors, errors
        finally:
            browser.close()
