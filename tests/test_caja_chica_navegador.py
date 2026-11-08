import json
from playwright.sync_api import sync_playwright, expect
from test_e2e_navegador import servidor
from test_caja_chica import tecnico


def test_justificacion_en_etapas_y_editor_conserva_detalles(app, auth_client, servidor, tecnico, tmp_path):
    cli, headers = tecnico
    result = cli.post('/form-pruebas/caja-chica/solicitar', headers=headers, json={
        'proyecto': 'CLARO', 'motivo': 'Justificación completa\nSegunda línea', 'banco': 'BCP',
        'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50', 'descripcion': 'Detalle original'},
                  {'tipo_gasto': 'Viáticos', 'monto': '30'}, {'tipo_gasto': 'Peajes', 'monto': '20'}]})
    assert result.status_code == 200, result.json
    sol = result.json['solicitud']
    auth_client.get('/caja-chica/')
    cookie = auth_client.get_cookie('session')
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1365, 'height': 600})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            states = [('PENDIENTE', 'validacion'), ('VALIDADO', 'deposito'), ('DEPOSITADO', 'por_rendir'),
                      ('DEPOSITADO', 'revision'), ('ARCHIVADO', 'archivado'), ('ANULADO', 'anuladas')]
            for estado, etapa in states:
                data = {**sol, 'estado': estado, 'etapas': [etapa], 'revision': {}, 'envio_tecnico': None,
                        'depositado_en': '2026-11-06T12:00' if estado == 'DEPOSITADO' else '',
                        'formulario': {'supervisor': 'Supervisor de prueba', 'site': 'DO_PLAZA_SOL_ICA_P4',
                                       'wo': 'CM-20260904-00000410', 'responsable_validacion': 'Jessica Cordero'}}
                page.route('**/api/caja-chica/solicitudes', lambda route, request, data=data: route.fulfill(json={'solicitudes': [data]}))
                page.goto(servidor + '/caja-chica/')
                page.locator('[data-tab="' + etapa + '"]').click()
                page.locator('#cc-lista a').filter(has_text=sol['codigo']).click()
                expect(page.locator('.cc-justificacion-texto')).to_have_text(sol['motivo'])
                if etapa in ('validacion', 'deposito', 'por_rendir'):
                    contenido = page.locator('#cc-solicitud-contenido')
                    assert contenido.evaluate('e=>e.scrollTop') == 0
                    ventana = page.locator('#cc-solicitud-dialogo').bounding_box()
                    cuerpo = contenido.bounding_box()
                    assert ventana['y'] + ventana['height'] - cuerpo['y'] - cuerpo['height'] <= 3
                    assert contenido.evaluate('e=>e.scrollHeight <= e.clientHeight + 1')
                    assert contenido.evaluate('e=>e.scrollWidth <= e.clientWidth + 1')
                    izquierda = page.locator('.cc-deposito-izquierda' if etapa != 'validacion' else '.cc-validacion-izquierda')
                    expect(izquierda.locator('.cc-ficha-titulo').first).to_have_text('Conceptos solicitados')
                    assert izquierda.locator('.cc-ficha-concepto').count() == len(sol['items']) + 1
                    expect(izquierda.locator('.cc-justificacion-texto')).to_have_text(sol['motivo'])
                    if etapa == 'deposito':
                        derecha = page.locator('.cc-deposito-derecha')
                        monto = derecha.locator('.cc-deposito-cabecera').bounding_box()
                        foto = derecha.locator('.cc-deposito-zona').bounding_box()
                        assert monto['y'] + monto['height'] <= foto['y']
                    if etapa == 'por_rendir':
                        derecha = page.locator('.cc-rendir-derecha')
                        timer = derecha.locator('.cc-sla-timer').bounding_box()
                        foto = derecha.locator('.cc-rendir-foto').bounding_box()
                        assert timer['y'] + timer['height'] <= foto['y']
                    page.screenshot(path=str(tmp_path / (etapa + '.png')))
                    print('CAPTURA', tmp_path / (etapa + '.png'))
                if estado == 'PENDIENTE':
                    expect(page.locator('#cc-solicitud-validar')).to_be_visible()
                    expect(page.locator('#cc-solicitud-anular')).to_be_visible()
                    assert page.locator('#cc-lista button[title="Rechazar"]').count() == 0
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


def test_portal_tecnico_con_tres_filtros_y_botones_redondos(app, servidor, tecnico):
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
            assert page.locator('#cc-filtros button').count() == 3
            assert 'Rechazado' not in page.locator('#cc-filtros').inner_text()
            page.locator('[data-filtro=validar]').click()
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


def test_acciones_abren_detalle_y_header_valida_o_anula(app, auth_client, servidor, tecnico):
    cli, headers = tecnico
    result = cli.post('/form-pruebas/caja-chica/solicitar', headers=headers, json={
        'proyecto': 'CLARO', 'motivo': 'Validar desde detalle', 'banco': 'BCP',
        'cuenta': '00123456789012345678', 'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}]})
    assert result.status_code == 200, result.json
    sol = result.json['solicitud']
    auth_client.get('/caja-chica/')
    cookie = auth_client.get_cookie('session')
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1365, 'height': 768})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page()
            posts = []
            page.on('request', lambda r: posts.append(r.url) if r.method == 'POST' else None)
            page.goto(servidor + '/caja-chica/')
            page.locator('[data-tab="validacion"]').click()
            for titulo in ('Validar', 'Anular'):
                page.locator('#cc-lista button[title="' + titulo + '"]').first.click()
                expect(page.locator('#cc-solicitud-dialogo')).to_be_visible()
                assert not posts
                page.locator('#cc-solicitud-dialogo [aria-label="Cerrar detalle"]').click()
            assert page.locator('#cc-lista button[title="Rechazar"]').count() == 0
            page.locator('#cc-lista a').filter(has_text=sol['codigo']).click()
            page.locator('#cc-solicitud-validar').click()
            confirmacion = page.get_by_role('dialog', name='Validar solicitud')
            expect(confirmacion).to_contain_text('pasará a Por depositar')
            expect(confirmacion.get_by_role('button', name='Validar')).to_have_css('border-radius', '50%')
            confirmacion.get_by_role('button', name='Cancelar').click()
            expect(confirmacion).to_be_hidden()
            assert not posts
            page.locator('#cc-solicitud-validar').click()
            with page.expect_response('**/api/caja-chica/*/validar') as response:
                confirmacion.get_by_role('button', name='Validar').click()
            assert response.value.status == 200
            assert response.value.json()['solicitud']['estado'] == 'VALIDADO'
            expect(page.locator('#cc-solicitud-validar')).to_be_hidden()
            expect(page.locator('#cc-solicitud-anular')).to_be_hidden()
            expect(page.locator('#cc-solicitud-rechazar')).to_be_visible()
            page.locator('#cc-solicitud-rechazar').click()
            page.locator('dialog.cc-motivo textarea').fill('Revisar solicitud antes del depósito')
            with page.expect_response('**/api/caja-chica/*/rechazar') as response:
                page.locator('dialog.cc-motivo .cc-motivo-ok').click()
            assert response.value.status == 200
            assert response.value.json()['solicitud']['estado'] == 'PENDIENTE'
            expect(page.locator('[data-tab="validacion"]')).to_have_attribute('aria-selected', 'true')
            expect(page.locator('#cc-solicitud-rechazar')).to_be_hidden()
            expect(page.locator('#cc-solicitud-anular')).to_be_visible()
            page.locator('#cc-solicitud-anular').click()
            page.locator('dialog.cc-motivo textarea').fill('Anulación de prueba')
            with page.expect_response('**/api/caja-chica/*/anular') as response:
                page.locator('dialog.cc-motivo .cc-motivo-ok').click()
            assert response.value.status == 200
            assert response.value.json()['solicitud']['estado'] == 'ANULADO'
            expect(page.locator('#cc-solicitud-anular')).to_be_hidden()
        finally:
            browser.close()
