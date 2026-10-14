"""Captura el dashboard nuevo de Cotizaciones (y el operativo, para comparar)."""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5001'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})

    page.goto(BASE + '/login')
    page.wait_for_load_state('networkidle')
    page.fill('input[name="username"]', 'zeno')
    page.fill('input[name="password"]', 'zeno123')
    cb = page.query_selector('input[name="legal_accept"]')
    if cb and not cb.is_checked():
        cb.check(force=True)
    page.click('#login-btn')
    page.wait_for_load_state('networkidle')

    # Paso de consentimiento, si aparece
    if page.query_selector('input[name="consent_step"]'):
        cb2 = page.query_selector('input[name="legal_accept"]')
        if cb2 and not cb2.is_checked():
            cb2.check(force=True)
        page.click('#login-btn')
        page.wait_for_load_state('networkidle')

    print('URL tras login:', page.url, '| titulo:', page.title())

    page.goto(BASE + '/analytics/cotizaciones')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1800)
    page.screenshot(path='scratch/dash_cotizaciones.png', full_page=True)
    print('cotizaciones =>', page.title())

    page.goto(BASE + '/analytics')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1800)
    page.screenshot(path='scratch/dash_operativo.png', full_page=True)
    print('operativo =>', page.title())

    browser.close()
print('OK')
