"""Abre el modal 'Detalle de Evidencia' y lo captura."""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5055'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1180, 'height': 800})
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

    # Entrar al módulo Rendicion desde el menú lateral
    enlace = page.query_selector('a.sidebar-link:has-text("Rendicion")')
    if enlace is None:
        enlace = page.query_selector('a.sidebar-link:has-text("RENDICION")')
    print('enlace rendicion:', bool(enlace))
    if enlace:
        enlace.click()
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2500)
    print('url:', page.url)
    ok = page.evaluate("""() => {
        const filas = (typeof rawData !== 'undefined' ? rawData : []);
        const fila = filas.find(r => r._key === 'R-EVIDENCIA');
        if (typeof rendAbrirDetalleEvidencia !== 'function') return 'sin funcion';
        if (!fila) return 'sin fila (' + filas.length + ' filas)';
        rendAbrirDetalleEvidencia('R-EVIDENCIA');
        return 'abierto';
    }""")
    print('modal:', ok)
    page.wait_for_timeout(1200)
    caja = page.evaluate("""() => {
        const c = document.querySelector('#evidencia-contenedor');
        if (!c) return null;
        const st = getComputedStyle(c);
        const tarjetas = [...c.querySelectorAll('.ev-card')].map(t => {
            const r = t.getBoundingClientRect();
            return {cat: t.dataset.cat, x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)};
        });
        return {display: st.display, columns: st.columnCount, ancho: Math.round(c.getBoundingClientRect().width), tarjetas};
    }""")
    print('contenedor:', caja)
    page.screenshot(path='scratch/ev_modal.png')
    browser.close()
print('OK')
