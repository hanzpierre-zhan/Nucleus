from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5020'


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


M = """() => {
  const p = document.querySelector('.di-page');
  const pr = p.getBoundingClientRect();
  const last = p.lastElementChild;
  const contentBottom = last.getBoundingClientRect().bottom - pr.top;
  const kids = [...p.children].map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().top - pr.top), Math.round(e.getBoundingClientRect().height)]);
  return {ch:p.clientHeight, sh:p.scrollHeight, contentBottom:Math.round(contentBottom), padTop:getComputedStyle(p).paddingTop, padBottom:getComputedStyle(p).paddingBottom, kids};
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for w, h in [(1352, 600), (1352, 674), (1920, 900)]:
        ctx = b.new_context(viewport={'width': w, 'height': h})
        page = ctx.new_page()
        login(page)
        for name, url, viz in [('cot', '/analytics/cotizaciones', '#dc-visual'), ('rend', '/analytics/rendicion', '#dr-visual')]:
            page.goto(BASE + url)
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(1000)
            for label, hide in [('full', None), ('noViz', viz), ('noVizNoMain', 'both')]:
                if hide == viz:
                    page.eval_on_selector(viz, 'e => e.style.display="none"')
                elif hide == 'both':
                    page.eval_on_selector(viz, 'e => e.style.display="none"')
                    page.eval_on_selector_all('.di-main-charts:not(.dc-viz-grid):not(.dr-viz-grid)', 'els => els.forEach(e => e.style.display="none")')
                page.wait_for_timeout(150)
                m = page.evaluate(M)
                print(w, h, name, label, 'ch', m['ch'], 'sh', m['sh'], 'contentBottom', m['contentBottom'], 'pad', m['padTop'], m['padBottom'])
                if label == 'full' or label == 'noVizNoMain':
                    print('    kids', m['kids'])
        ctx.close()
    b.close()
