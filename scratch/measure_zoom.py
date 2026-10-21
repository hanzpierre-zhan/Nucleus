from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:5020'
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    ctx=b.new_context(viewport={'width':1352,'height':674})
    page=ctx.new_page()
    page.goto(BASE+'/login'); page.wait_for_load_state('networkidle')
    page.fill('input[name="username"]','hvargas'); page.fill('input[name="password"]','zeno123')
    cb=page.query_selector('input[name="legal_accept"]')
    if cb and not cb.is_checked(): cb.check(force=True)
    page.click('#login-btn'); page.wait_for_load_state('networkidle')
    page.goto(BASE+'/analytics/cotizaciones'); page.wait_for_timeout(800)
    print(page.evaluate("""() => ({innerW:innerWidth,innerH:innerHeight,dpr:devicePixelRatio,bodyZoom:getComputedStyle(document.body).zoom,htmlZoom:getComputedStyle(document.documentElement).zoom,bodyFont:getComputedStyle(document.body).fontSize,pageRect:document.querySelector('.di-page').getBoundingClientRect().width, pageH:document.querySelector('.di-page').getBoundingClientRect().height})"""))
    b.close()
