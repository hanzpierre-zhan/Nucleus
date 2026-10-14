"""Captura las cabeceras de los tres dashboards para revisar la alineación."""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5055'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1600, 'height': 900})
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
    print('login ->', page.url)

    for nombre, ruta in [('rend', '/analytics/rendicion'),
                         ('coti', '/analytics/cotizaciones'),
                         ('prod', '/analytics')]:
        page.goto(BASE + ruta)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1200)
        # Caja de la barra de filtros para medir su alineación real
        caja = page.evaluate("""() => {
            const f = document.querySelector('.di-head .di-filters');
            if (!f) return null;
            const r = f.getBoundingClientRect();
            return {left: Math.round(r.left), right: Math.round(r.right),
                    ancho: Math.round(r.width), ventana: window.innerWidth,
                    justify: getComputedStyle(f).justifyContent,
                    wrap: getComputedStyle(f).flexWrap};
        }""")
        print(nombre, caja)
        page.screenshot(path='scratch/shot_%s.png' % nombre,
                        clip={'x': 0, 'y': 0, 'width': 1600, 'height': 330})
    browser.close()
print('OK')
