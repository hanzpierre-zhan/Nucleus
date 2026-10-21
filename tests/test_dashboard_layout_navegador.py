"""Contratos de legibilidad comunes con datos aislados y cifras largas."""
import json
from pathlib import Path

import pytest

playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor  # noqa: F401
from db import db
from models import NucleusData, Proyecto


@pytest.mark.parametrize('modo', ['cotizaciones', 'rendicion'])
def test_tarjetas_legibles_en_temas_y_anchos(app, auth_client, servidor, modo, tmp_path):
    with app.app_context():
        modulo = 'Rendicion' if modo == 'rendicion' else 'Cotizaciones'
        pid = Proyecto.query.filter_by(nombre=modulo).one().id
        ids = []
        for n in range(20):
            label = 'Responsable de operaciones y seguimiento de proyectos regionales ' + str(n)
            key = 'VISUAL-DASH-' + str(n)
            if modo == 'rendicion':
                row = {'Nombre del proyecto': 'ENTEL', 'ESTADO': ('PENDIENTE', 'VALIDADO', 'DEPOSITADO', 'CON SUSTENTO')[n % 4],
                       'Marca temporal': '2026-10-17', 'FECHA PAGO': '2026-10-18', 'Tipo de presupuesto': 'Gasto Cobra', 'SOLICITADO POR': label, 'VALIDADO POR': label,
                       'Monto total del depósito': '123456789.89', 'MONTO PAGO': '123456789.89'}
            else:
                row = {'CLIENTE': 'ENTEL', 'ESTADO COTIZACION': ('En Aprobación', 'Aprobado')[n % 2],
                       'N° COTIZACION': key, 'FECHA': '2026-10-17', 'SUB TOTAL + FEE': '123456789.89',
                       'SOLICITADO POR': label, 'COTIZADO POR': label, 'TIPO DE COTIZACION': label}
            f = NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps(row))
            db.session.add(f); db.session.flush(); ids.append(f.id)
        db.session.commit()
    try:
        cookie = auth_client.get_cookie('session')
        with playwright_api.sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(viewport={'width': 1920, 'height': 1080})
                context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
                page = context.new_page(); errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(servidor + '/analytics/' + modo, wait_until='networkidle')
                page.wait_for_function('window.Chart && Object.keys(Chart.instances).length > 0')
                folder = tmp_path
                for dark in (False, True):
                    page.evaluate('(dark) => document.body.classList.toggle("dark-mode", dark)', dark)
                    for width, height in ((1352, 674), (1920, 900), (390, 844)):
                        page.set_viewport_size({'width': width, 'height': height})
                        playwright_api.expect(page.locator('#df-kpis article').first).to_be_visible()
                        assert page.locator('.di-finance details').count() == 0
                        assert page.locator('#dq-panel,#di-secondary,#dc-responsables').count() == 0
                        page.wait_for_function('''() => [...document.querySelectorAll('#df-kpis strong')]
                            .every(e => e.scrollWidth <= e.clientWidth + 1)''')
                        metrics = page.locator('.di-finance').evaluate('(e) => ({width:e.clientWidth, scrollWidth:e.scrollWidth})')
                        assert metrics['scrollWidth'] <= metrics['width'] + 1, (modo, dark, width, metrics)
                        for canvas in page.locator('.df-grid canvas:visible').all():
                            assert canvas.evaluate('(e) => e.width > 0 && e.height > 0')
                        page.screenshot(path=str(folder / (modo + '-' + str(dark) + '-' + str(width) + '.png')))
                # Los filtros actualizan totales sin acumular instancias de gráficos.
                options = page.locator('#df-state option').all_text_contents()
                if len(options) > 1:
                    page.get_by_role('combobox', name='Estado', exact=True).select_option(label=options[1])
                    playwright_api.expect(page.locator('#df-caption')).to_contain_text('registros')
                    page.get_by_role('button', name='Limpiar', exact=True).click()
                    playwright_api.expect(page.get_by_role('combobox', name='Estado', exact=True)).to_have_value('')
                assert page.locator('#df-kpis article').count() == (6 if modo == 'rendicion' else 2)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.parametrize('modo', ['produccion', 'cobranza'])
def test_modulos_restaurados_conservan_diseno_previo(app, auth_client, servidor, modo):
    cookie = auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1352, 'height': 674})
            context.add_cookies([{'name': 'session', 'value': cookie.value, 'domain': '127.0.0.1', 'path': '/'}])
            page = context.new_page(); errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(servidor + ('/analytics' if modo == 'produccion' else '/analytics/cobranza'), wait_until='networkidle')
            assert page.locator('link[href*="dashboard-layout.css"]').count() == 0
            assert page.locator('script[src*="dashboard-graficos.js"]').count() == 0
            assert len(page.locator('.di-charts').evaluate('(e) => getComputedStyle(e).gridTemplateColumns').split()) == 4
            assert page.locator('.di-charts .di-card').first.evaluate('(e) => parseFloat(getComputedStyle(e).height)') <= 240
            folder = Path('C:/Users/Hanz/Documents/Codex/2026-10-19/realtime-voice-chat/outputs')
            page.screenshot(path=str(folder / (modo + '-restaurado-1352x674.png')))
            assert not errors, errors
        finally:
            browser.close()
