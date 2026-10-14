"""Mide la alineación real de la barra de filtros en varios anchos."""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5055'
RUTAS = [('rend', '/analytics/rendicion'), ('coti', '/analytics/cotizaciones'), ('prod', '/analytics')]

MEDIDA = """() => {
    const f = document.querySelector('.di-head .di-filters');
    if (!f) return null;
    const caja = f.getBoundingClientRect();
    const hijos = [...f.children].map(c => c.getBoundingClientRect());
    const ultimo = hijos.length ? Math.round(Math.max(...hijos.map(r => r.right))) : null;
    const primero = hijos.length ? Math.round(Math.min(...hijos.map(r => r.left))) : null;
    return {ventana: window.innerWidth, contenedor: [Math.round(caja.left), Math.round(caja.right)],
            primerFiltro: primero, ultimoFiltro: ultimo,
            huecoDerecha: Math.round(window.innerWidth - ultimo),
            justify: getComputedStyle(f).justifyContent};
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for ancho in (1920, 1600, 1280, 1024, 900):
        page = browser.new_page(viewport={'width': ancho, 'height': 900})
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
        print('=== ancho %d ===' % ancho)
        for nombre, ruta in RUTAS:
            page.goto(BASE + ruta)
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(400)
            print('   %-5s %s' % (nombre, page.evaluate(MEDIDA)))
        if ancho == 1024:
            for nombre, ruta in RUTAS:
                page.goto(BASE + ruta)
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(500)
                page.screenshot(path='scratch/shot_%s_1024.png' % nombre, clip={'x': 0, 'y': 0, 'width': ancho, 'height': 300})
        page.close()
    browser.close()
print('OK')
