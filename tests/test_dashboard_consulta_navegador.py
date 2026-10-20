import json
from pathlib import Path

import pytest

playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor  # noqa: F401
from db import db
from models import NucleusData, Proyecto


@pytest.mark.parametrize('modo', ['cotizaciones', 'rendicion'])
def test_filtros_montos_fechas_y_detalle_en_navegador(app, auth_client, servidor, modo):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones' if modo == 'cotizaciones' else 'Rendicion').one().id
        ids = []
        for n, cliente in enumerate(('ENTEL', 'CLARO'), 1):
            key = 'DASH-MEJORA-' + str(n)
            if modo == 'cotizaciones':
                d = {'N° COTIZACION': key, 'CLIENTE': cliente, 'ESTADO COTIZACION': 'En Aprobación' if n == 1 else 'Aprobado',
                     'FECHA': '2026-09-01', 'FECHA COTIZADO': '2026-10-01', 'FECHA APROBACION': '2026-10-03',
                     'TIPO DE GASTO': 'Gasto Cobra' if n == 1 else 'Refacturable',
                     'TIPO GASTO APROBACION': '' if n == 1 else 'Proveedor',
                     'SUB TOTAL + FEE': str(n * 1234567.89), 'SOLICITADO POR': 'solicita-' + str(n), 'COTIZADO POR': 'genera-' + str(n)}
            else:
                d = {'Nombre del proyecto': cliente, 'ESTADO': 'DEPOSITADO' if n == 1 else 'CON SUSTENTO',
                     'Marca temporal': '2026-09-01', 'FECHA PAGO': '2026-10-01', 'Monto total del depósito': '100',
                     'MONTO PAGO': 0 if n == 1 else 80, 'Técnico beneficiario': 'persona-' + str(n),
                     'Responsable de la validación': 'asignado-' + str(n), 'VALIDADO POR': 'valido-' + str(n)}
            d['DEPARTAMENTO'] = 'Ica' if n == 1 else 'Junín'
            f = NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps(d))
            db.session.add(f); db.session.flush(); ids.append(f.id)
        db.session.commit()
    try:
        cookie = auth_client.get_cookie('session')
        with playwright_api.sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(viewport={'width': 1365, 'height': 900})
                context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
                page = context.new_page(); errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(servidor + '/analytics/' + modo, wait_until='networkidle')
                page.wait_for_function("document.getElementById('dq-selection').textContent.length > 0")
                if modo == 'cotizaciones':
                    detail = page.locator('#dc-responsables')
                    assert not detail.evaluate('(e) => e.open')
                    assert detail.evaluate('(e) => e.previousElementSibling.classList.contains("di-order-details")')
                    for width in (1365, 390):
                        page.set_viewport_size({'width': width, 'height': 900})
                        page.locator('.dc-money').scroll_into_view_if_needed()
                        assert page.locator('#dc-money').evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
                        for amount in page.locator('#dc-money .di-bar-metrics > b').all():
                            assert amount.evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
                            assert amount.evaluate('(e) => e.getBoundingClientRect().height < 25')
                        assert page.locator('#dc-money .di-bar-track').first.evaluate('(e) => parseFloat(getComputedStyle(e).height)') >= 8
                        folder = Path('backups/dashboard-mejoras-20261019'); folder.mkdir(parents=True, exist_ok=True)
                        page.locator('.dc-money').screenshot(path=str(folder / ('dinero-' + str(width) + '.png')))
                    page.set_viewport_size({'width': 1365, 'height': 900})
                    assert '1,234,567.89' in page.locator('#dc-money').inner_text()
                    detail.locator('summary').click()
                    assert page.locator('#dc-matrix').is_visible()
                    detail.locator('summary').click()
                page.locator('#dq-panel > details').first.locator('summary').first.click()
                page.locator('#dq-search').fill('DASH-MEJORA')
                page.wait_for_function("document.getElementById('dq-selection').textContent.startsWith('2 ')")
                page.locator('#dq-department').select_option('Ica')
                page.wait_for_function("document.getElementById('dq-selection').textContent.startsWith('1 ')")
                assert page.locator('#dc-kpi-total' if modo == 'cotizaciones' else '#dr-kpi-total').text_content() == '1'
                if modo == 'rendicion':
                    page.locator('#dq-date').select_option('dia_pago')
                    page.locator('#di-month').select_option('2026-10')
                    assert '0.00' in page.locator('#dq-summary').inner_text()
                else:
                    page.locator('#dq-department').select_option('')
                    page.locator('#dq-approval').select_option('Proveedor')
                    page.wait_for_function("document.getElementById('dq-selection').textContent.startsWith('1 ')")
                    page.locator('#dq-date').select_option('dia_aprobacion')
                    page.locator('#di-month').select_option('2026-10')
                    assert page.locator('#dc-kpi-sustentar').inner_text() == '1'
                page.locator('.dq-analysis > summary').click()
                page.locator('#dq-group').select_option('solicito')
                page.locator('#dq-matrix button').filter(has_text='1 casos').first.click()
                assert page.locator('#dq-cases-count').inner_text() == '(1)'
                href = page.locator('#dq-cases a').first.get_attribute('href')
                assert '/switch_project/' + str(pid) in href and 'caso' in href
                folder = Path('backups/dashboard-mejoras-20261019'); folder.mkdir(parents=True, exist_ok=True)
                page.locator('#dq-panel').screenshot(path=str(folder / (modo + '-consulta.png')))
                page.locator('#di-clear').click()
                assert page.locator('#dq-date').input_value() == 'dia_solicitud'
                assert page.locator('#dq-department').input_value() == ''
                assert page.locator('#dq-approval' if modo == 'cotizaciones' else '#dq-validator').input_value() == ''
                # El enlace abre el módulo y filtra el caso exacto para actuar.
                page.goto(servidor + href, wait_until='networkidle')
                assert not errors, errors
                page.screenshot(path=str(folder / (modo + '-destino.png')))
                page.wait_for_selector('.tabulator-row', timeout=20000)
                assert page.locator('.tabulator-row').count() == 1
                assert not errors
            finally:
                browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()
