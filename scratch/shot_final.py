"""Captura la cabecera de Rendición a 1280px (donde tú lo veías mal)."""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5055'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    page.goto(BASE + '/login')
    page.wait_for_load_state('networkidle')
    page.fill('input[name="username"]', 'zeno')
    page.fill('input[name="password"]', 'zeno123')
    cb = page.query_selector('input[name="legal_accept"]')
    if cb and not cb.is_checked():
        cb.check(force=True)
    page.click('#login-btn')
    page.wait_for_load_state('networkidle')
    if page.query_selector('input[name="consent_step"]'):
        cb2 = page.query_selector('input[name="legal_accept"]')
        if cb2 and not cb2.is_checked():
            cb2.check(force=True)
        page.click('#login-btn')
        page.wait_for_load_state('networkidle')
    page.goto(BASE + '/analytics/rendicion')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    page.screenshot(path='scratch/ok_rend_1280.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 300})
    browser.close()
print('OK')
