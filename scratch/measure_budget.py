from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5020'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for w, h in [(1352, 674), (1352, 600), (1920, 900)]:
        ctx = b.new_context(viewport={'width': w, 'height': h})
        page = ctx.new_page()
        page.goto(BASE + '/login'); page.wait_for_load_state('networkidle')
        page.fill('input[name="username"]', 'hvargas'); page.fill('input[name="password"]', 'zeno123')
        cb = page.query_selector('input[name="legal_accept"]')
        if cb and not cb.is_checked(): cb.check(force=True)
        page.click('#login-btn'); page.wait_for_load_state('networkidle')
        for name, url, viz in [('cot','/analytics/cotizaciones','#dc-visual'), ('rend','/analytics/rendicion','#dr-visual')]:
            page.goto(BASE + url); page.wait_for_load_state('networkidle'); page.wait_for_timeout(800)
            page.eval_on_selector(viz, 'e => e.style.display="none"')
            page.wait_for_timeout(200)
            base = page.evaluate("""() => {const p=document.querySelector('.di-page');return {cw:p.clientWidth,ch:p.clientHeight,sh:p.scrollHeight,kids:[...p.children].map(e=>[e.className||e.tagName,Math.round(e.getBoundingClientRect().height)])}}""")
            print(w, h, name, base)
        ctx.close()
    b.close()
