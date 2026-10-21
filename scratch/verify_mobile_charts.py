from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5020'
OUT = 'scratch/verify-dash'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 390, 'height': 844})
    page = ctx.new_page()
    page.goto(BASE + '/login')
    page.wait_for_load_state('networkidle')
    page.fill('input[name="username"]', 'hvargas')
    page.fill('input[name="password"]', 'zeno123')
    cb = page.query_selector('input[name="legal_accept"]')
    if cb and not cb.is_checked():
        cb.check(force=True)
    page.click('#login-btn')
    page.wait_for_load_state('networkidle')

    for name, url, sel in [('cotizaciones-movil-graficos', '/analytics/cotizaciones', '#dc-visual'),
                            ('rendicion-movil-graficos', '/analytics/rendicion', '#dr-visual')]:
        page.goto(BASE + url)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)
        page.eval_on_selector(sel, "el => el.scrollIntoView({block:'start'})")
        page.wait_for_timeout(500)
        page.screenshot(path=f'{OUT}/{name}.png')
        widths = page.eval_on_selector_all(sel + " canvas", "els => els.map(c => [c.id, c.getBoundingClientRect().width, c.getBoundingClientRect().height])")
        print(name, widths)

    browser.close()
