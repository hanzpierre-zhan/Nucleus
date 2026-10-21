"""Verificación visual de los dashboards de Cotizaciones y Rendición."""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5020'
OUT = Path('scratch/verify-dash')
OUT.mkdir(parents=True, exist_ok=True)
log = {'console': [], 'failed': [], 'pages': {}}


def login(page):
    page.goto(BASE + '/login')
    page.wait_for_load_state('networkidle')
    page.fill('input[name="username"]', 'hvargas')
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


def inspect(page, name):
    data = page.evaluate("""() => {
        const ids = [...document.querySelectorAll('canvas')].map(c => c.id);
        const dup = ids.filter((id, i) => id && ids.indexOf(id) !== i);
        const instances = window.Chart ? Object.keys(window.Chart.instances || {}).length : -1;
        const visibleCharts = [...document.querySelectorAll('.di-main-charts canvas, #dc-visual canvas, .dr-viz-grid canvas')]
            .filter(c => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0).length;
        const detailsOpen = [...document.querySelectorAll('details')].filter(d => d.open).map(d => d.id || d.className);
        return {canvasIds: ids, dup, instances, visibleCharts, detailsOpen,
                detailCount: document.querySelectorAll('details').length,
                scrollHeight: document.documentElement.scrollHeight};
    }""")
    page.screenshot(path=str(OUT / f'{name}-arriba.png'))
    page.evaluate("""() => {
        const page = document.querySelector('.di-page');
        if (page && page.scrollHeight > page.clientHeight) page.scrollTop = page.scrollHeight;
        window.scrollTo(0, document.body.scrollHeight);
    }""")
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / f'{name}-abajo.png'))
    page.evaluate("""() => {
        const page = document.querySelector('.di-page');
        if (page) page.scrollTop = 0;
        window.scrollTo(0, 0);
    }""")
    page.wait_for_timeout(300)
    return data


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = ctx.new_page()

    def on_console(msg):
        if msg.type in ('error', 'warning'):
            log['console'].append({'type': msg.type, 'text': msg.text})

    def on_failed(req):
        log['failed'].append({'url': req.url, 'failure': req.failure})

    page.on('console', on_console)
    page.on('requestfailed', on_failed)
    login(page)
    print('login url', page.url)

    # Cotizaciones
    page.goto(BASE + '/analytics/cotizaciones')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1800)
    log['pages']['cotizaciones'] = inspect(page, 'cotizaciones')
    # Cambio de filtro: no debe duplicar canvas ni instancias
    before = page.evaluate("() => ({c: document.querySelectorAll('canvas').length, i: Object.keys(window.Chart.instances||{}).length})")
    opts = page.eval_on_selector_all('#di-type option', 'els => els.map(e => e.value).filter(Boolean)')
    if opts:
        page.select_option('#di-type', opts[0])
        page.wait_for_timeout(1200)
    after = page.evaluate("() => ({c: document.querySelectorAll('canvas').length, i: Object.keys(window.Chart.instances||{}).length})")
    log['pages']['cotizaciones']['filtro'] = {'before': before, 'after': after}
    page.screenshot(path=str(OUT / 'cotizaciones-filtro.png'))

    # Rendición
    page.goto(BASE + '/analytics/rendicion')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1800)
    log['pages']['rendicion'] = inspect(page, 'rendicion')
    before = page.evaluate("() => ({c: document.querySelectorAll('canvas').length, i: Object.keys(window.Chart.instances||{}).length})")
    opts = page.eval_on_selector_all('#di-budget option', 'els => els.map(e => e.value).filter(Boolean)')
    if opts:
        page.select_option('#di-budget', opts[0])
        page.wait_for_timeout(1200)
    after = page.evaluate("() => ({c: document.querySelectorAll('canvas').length, i: Object.keys(window.Chart.instances||{}).length})")
    log['pages']['rendicion']['filtro'] = {'before': before, 'after': after}
    page.screenshot(path=str(OUT / 'rendicion-filtro.png'))

    # Móvil 390x844
    mob = browser.new_context(viewport={'width': 390, 'height': 844})
    mp = mob.new_page()
    mp.on('console', lambda m: log['console'].append({'type': m.type, 'text': m.text}) if m.type in ('error', 'warning') else None)
    mp.on('requestfailed', on_failed)
    login(mp)
    for name, url in [('cotizaciones-movil', '/analytics/cotizaciones'), ('rendicion-movil', '/analytics/rendicion')]:
        mp.goto(BASE + url)
        mp.wait_for_load_state('networkidle')
        mp.wait_for_timeout(1600)
        info = mp.evaluate("""() => ({
            overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
            bodyScrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            canvasCount: document.querySelectorAll('canvas').length,
            dup: [...document.querySelectorAll('canvas')].map(c=>c.id).filter((id,i,a)=>id && a.indexOf(id)!==i),
        })""")
        log['pages'][name] = info
        mp.screenshot(path=str(OUT / f'{name}-arriba.png'))
        mp.evaluate("""() => { const p=document.querySelector('.di-page'); if(p) p.scrollTop=p.scrollHeight; window.scrollTo(0, document.body.scrollHeight); }""")
        mp.wait_for_timeout(600)
        mp.screenshot(path=str(OUT / f'{name}-abajo.png'))
        mp.evaluate("""() => { const p=document.querySelector('.di-page'); if(p) p.scrollTop=0; window.scrollTo(0,0); }""")

    browser.close()

(OUT / 'reporte.json').write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(log, ensure_ascii=False, indent=2))
