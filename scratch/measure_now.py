from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5020'
VIEWPORTS = [(1352, 600), (1352, 674), (1920, 900)]


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


JS = """() => {
  const p = document.querySelector('.di-page');
  const pr = p.getBoundingClientRect();
  const kids = [...p.children].map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().height)]);
  const charts = [...p.querySelectorAll('.di-main-charts')].map(g => ({cls: g.className, h: Math.round(g.getBoundingClientRect().height), cards: [...g.children].map(c => Math.round(c.getBoundingClientRect().height))}));
  const canvas = [...p.querySelectorAll('canvas')].map(c => [c.id, Math.round(c.getBoundingClientRect().width), Math.round(c.getBoundingClientRect().height)]);
  return {clientWidth:p.clientWidth, clientHeight:p.clientHeight, scrollHeight:p.scrollHeight, rectH:Math.round(pr.height), kids, charts, canvas};
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for w, h in VIEWPORTS:
        ctx = b.new_context(viewport={'width': w, 'height': h})
        page = ctx.new_page()
        login(page)
        for name, url, viz in [('cot', '/analytics/cotizaciones', '#dc-visual'), ('rend', '/analytics/rendicion', '#dr-visual')]:
            page.goto(BASE + url)
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(1200)
            full = page.evaluate(JS)
            print('===', w, h, name, 'client', full['clientWidth'], 'x', full['clientHeight'], 'scroll', full['scrollHeight'])
            print('   kids', full['kids'])
            print('   charts', full['charts'])
            print('   canvas', full['canvas'])
            page.eval_on_selector(viz, 'e => e.style.display="none"')
            page.wait_for_timeout(200)
            base = page.evaluate("""() => {const p=document.querySelector('.di-page');return {ch:p.clientHeight,sh:p.scrollHeight,kids:[...p.children].map(e=>[e.id||e.className||e.tagName,Math.round(e.getBoundingClientRect().height)])}}""")
            print('   base-no-viz', base)
            page.eval_on_selector(viz, 'e => e.style.display=""')
        ctx.close()
    b.close()
