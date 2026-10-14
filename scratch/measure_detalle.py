"""Detalle hijo por hijo de la barra de filtros, en varios anchos."""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5055'
RUTAS = [('rend', '/analytics/rendicion'), ('coti', '/analytics/cotizaciones'), ('prod', '/analytics')]

DETALLE = """() => {
    const f = document.querySelector('.di-head .di-filters');
    const cs = getComputedStyle(f);
    const caja = f.getBoundingClientRect();
    const hijos = [...f.children].map(c => {
        const r = c.getBoundingClientRect();
        const t = (c.querySelector('label') || c).textContent.trim().split('\\n')[0].slice(0, 14);
        return {t, l: Math.round(r.left), r: Math.round(r.right), fila: Math.round(r.top)};
    });
    const filas = [...new Set(hijos.map(h => h.fila))].length;
    return {ventana: window.innerWidth, contenedor: [Math.round(caja.left), Math.round(caja.right)],
            justify: cs.justifyContent, wrap: cs.flexWrap, flex: cs.flex, basis: cs.flexBasis,
            display: cs.display, filas, hijos};
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for ancho in (1920, 1440, 1280, 1100, 1024, 900):
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
        for nombre, ruta in RUTAS:
            page.goto(BASE + ruta)
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(300)
            d = page.evaluate(DETALLE)
            print('=== %s @ %d ===' % (nombre, ancho))
            print('   justify=%s wrap=%s flex=%s basis=%s filas=%d contenedor=%s' % (
                d['justify'], d['wrap'], d['flex'], d['basis'], d['filas'], d['contenedor']))
            print('   ' + ' | '.join('%s[%d-%d]' % (h['t'], h['l'], h['r']) for h in d['hijos']))
        page.close()
    browser.close()
print('OK')
