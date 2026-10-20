"""Contratos de legibilidad comunes con datos aislados y cifras largas."""
import json
from pathlib import Path

import pytest

playwright_api = pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor  # noqa: F401
from db import db
from models import NucleusData, Proyecto


@pytest.mark.parametrize('modo', ['cotizaciones', 'rendicion'])
def test_tarjetas_legibles_en_temas_y_anchos(app, auth_client, servidor, modo):
    with app.app_context():
        modulo = 'Rendicion' if modo == 'rendicion' else 'Cotizaciones'
        pid = Proyecto.query.filter_by(nombre=modulo).one().id
        ids = []
        for n in range(20):
            label = 'Responsable de operaciones y seguimiento de proyectos regionales ' + str(n)
            key = 'VISUAL-DASH-' + str(n)
            if modo == 'rendicion':
                row = {'Nombre del proyecto': 'ENTEL', 'ESTADO': ('PENDIENTE', 'VALIDADO', 'DEPOSITADO', 'CON SUSTENTO')[n % 4],
                       'Marca temporal': '2026-10-17', 'SOLICITADO POR': label, 'VALIDADO POR': label,
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
                page.wait_for_selector('.di-ranking .di-bar-row')
                folder = Path('C:/Users/Hanz/Documents/Codex/2026-10-19/realtime-voice-chat/outputs')
                folder.mkdir(parents=True, exist_ok=True)
                measurements = []
                # Chrome de 768 px de alto deja aproximadamente 674 px útiles.
                for dark in (False, True):
                    page.evaluate('(dark) => document.body.classList.toggle("dark-mode", dark)', dark)
                    for width, height in ((1352, 674), (1352, 600), (1920, 900), (390, 844)):
                        page.set_viewport_size({'width': width, 'height': height})
                        page.wait_for_timeout(120)
                        page.locator('.di-page').evaluate('(e) => e.scrollTop = 0')
                        assert page.locator('.di-executive > details[open]').count() == 0
                        assert page.locator('#dq-panel .dq-analysis').count() == 0
                        assert page.locator('#dq-analysis').evaluate('(e) => Boolean(e.compareDocumentPosition(document.querySelector(".di-main-charts")) & Node.DOCUMENT_POSITION_PRECEDING)')
                        metrics = page.evaluate('''() => {
                            const p = document.querySelector('.di-page');
                            return {width:p.clientWidth, scrollWidth:p.scrollWidth, height:p.clientHeight, scrollHeight:p.scrollHeight,
                                    documentHeight:document.scrollingElement.scrollHeight, viewport:innerHeight,
                                    availablePixels:p.getBoundingClientRect().height, contentBottom:p.lastElementChild.getBoundingClientRect().bottom-p.getBoundingClientRect().top};
                        }''')
                        measurements.append(dict(viewportWidth=width, viewportHeight=height, dark=dark, **metrics))
                        assert metrics['scrollWidth'] <= metrics['width'] + 1, (modo, dark, width, height, metrics)
                        if width >= 1000:
                            assert metrics['scrollHeight'] <= metrics['height'] + 1, (modo, dark, width, height, metrics)
                            assert metrics['documentHeight'] <= metrics['viewport'] + 1, metrics
                        problems = page.evaluate('''() => [...document.querySelectorAll('.di-main-charts .di-card, .di-main-charts .di-bar-row, .di-main-charts .di-bar-name, .di-main-charts .di-bar-metrics b')]
                            .filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)
                            .map(e => ({tag:e.className,text:e.textContent.slice(0,80)}))''')
                        assert not problems, problems
                        if modo == 'cotizaciones':
                            assert not page.locator('#dc-responsables').evaluate('(e) => e.open')
                        page.screenshot(full_page=width < 1000, path=str(folder / (modo + '-compacto-' + ('oscuro' if dark else 'claro') + '-' + str(width) + 'x' + str(height) + '.png')))
                (folder / (modo + '-dimensiones.json')).write_text(json.dumps(measurements, indent=2), encoding='utf-8')
                # Los secundarios y la concentración siguen disponibles, cerrados al entrar.
                page.locator('#di-secondary > summary').click()
                assert page.locator('#di-daily').is_visible()
                page.locator('#di-secondary > summary').click()
                page.locator('#dq-analysis > summary').click()
                assert page.locator('#dq-matrix').is_visible()
                page.locator('#dq-analysis > summary').click()
                more = page.locator('.di-main-charts .di-ranking-more').first
                if more.count():
                    more.click(); assert more.get_attribute('aria-expanded') == 'true'
                    if modo == 'cotizaciones':
                        assert page.locator('#dc-cli-users .di-bar-row').count() == 10
                    more.click(); assert more.get_attribute('aria-expanded') == 'false'
                paired = page.locator('.di-ranking-controls').first
                if paired.count():
                    paired.get_by_role('button', name='Monto', exact=True).click()
                    assert paired.get_by_role('button', name='Monto', exact=True).get_attribute('aria-pressed') == 'true'
                    assert 'S/' in paired.locator('..').locator('.di-bar-metrics b').first.inner_text()
                    paired.get_by_role('button', name='Cantidad', exact=True).click()
                    assert paired.get_by_role('button', name='Cantidad', exact=True).get_attribute('aria-pressed') == 'true'
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
