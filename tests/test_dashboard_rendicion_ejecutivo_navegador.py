import json
import pytest
playwright_api=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import NucleusData,Proyecto


def test_panel_ejecutivo_reconcilia_y_se_adapta(app,auth_client,servidor,tmp_path):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        ids=[]
        for n in range(96):
            client=['Entel','Claro','Integratel','Entel - Pext'][n%4]
            technician=['Carlos Mendoza','Juan Pérez','María Torres','Luis García','José Ramírez','Ana Castillo','Pedro Sánchez','Rosa Medina'][n//4%8]
            data={'Nombre del proyecto':client,'Documento del beneficiario':str(10000000+n%32),
                'Técnico beneficiario':technician,'ESTADO':'DEPOSITADO' if n<88 else 'SUSTENTADO',
                'Responsable de la validación':['Rosmeri','Mónica','Edwin','Luz','Héctor'][n%5],
                'Tipo de presupuesto':'GASTO COBRA' if n%3 else 'REFACTURABLE','MONTO PAGO':str(100+n*37.5),
                'Marca temporal':f'2026-{9+n%2:02d}-{1+n%21:02d}','FECHA PAGO':f'2026-10-{1+n%21:02d}'}
            row=NucleusData(proyecto_id=pid,key_value='EXEC-QA-'+str(n),data_json=json.dumps(data))
            db.session.add(row);db.session.flush();ids.append(row.id)
        db.session.commit()
    try:
        cookie=auth_client.get_cookie('session')
        with playwright_api.sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                context=browser.new_context(viewport={'width':1920,'height':1200})
                context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(servidor+'/analytics/rendicion',wait_until='networkidle')
                page.wait_for_function('Object.keys(Chart.instances).length===8')
                assert page.locator('.re-beneficiary').count()==3
                assert page.locator('#re-comparison-total').inner_text()
                assert 'CON SUSTENTO' in page.locator('#re-comparison-note').inner_text()
                assert page.locator('#re-clients-legend').inner_text().count('S/')==4
                assert page.evaluate('()=>Chart.getChart("re-applicants").config.plugins.some(p=>p.id==="executiveAmounts")')
                assert page.evaluate('()=>Chart.getChart("re-trend").config.plugins.some(p=>p.id==="trendAmounts")')
                paid_total=sum(100+n*37.5 for n in range(88,96))
                assert page.evaluate('()=>Chart.getChart("re-comparison").data.datasets.reduce((s,d)=>s+d.data.reduce((a,b)=>a+b,0),0)')==paid_total
                assert page.locator('#df-kpis article').count()==6
                names=page.evaluate('()=>Chart.getChart("re-entel").data.labels')
                assert names and all(not str(n).isdigit() for n in names)
                for dark in (False,True):
                    page.evaluate('(dark)=>document.body.classList.toggle("dark-mode",dark)',dark)
                    for width in (1920,1352,768,390):
                        page.set_viewport_size({'width':width,'height':1200 if width==1920 else 900})
                        page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                        assert page.locator('.rend-executive').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                        assert page.locator('#re-clients-legend').evaluate('(e)=>e.lastElementChild.getBoundingClientRect().bottom<=e.closest("article").getBoundingClientRect().bottom-8')
                        assert page.locator('#df-kpis strong').evaluate_all('(nodes)=>nodes.every(e=>e.scrollWidth<=e.clientWidth+1)')
                        for canvas in page.locator('.re-grid canvas:visible').all():
                            assert canvas.evaluate('(e)=>e.width>0&&e.height>0')
                        page.locator('.rend-executive').evaluate('(e)=>e.scrollTop=0')
                        page.screenshot(path=str(tmp_path/f'rendicion-{dark}-{width}.png'),animations='disabled')
                        if width==390:
                            page.locator('#re-integratel').scroll_into_view_if_needed()
                            page.screenshot(path=str(tmp_path/f'rendicion-rankings-{dark}-{width}.png'),animations='disabled')
                page.set_viewport_size({'width':1920,'height':1200})
                page.locator('#re-period').select_option('month')
                assert len(page.evaluate('()=>Chart.getChart("re-trend").data.labels'))==2
                page.locator('#df-operator').select_option('ENTEL')
                assert 'ENTEL' in page.locator('#df-active').inner_text()
                assert page.evaluate('()=>Chart.getChart("re-clients").data.labels')==['ENTEL']
                page.locator('#df-clear').click()
                assert page.evaluate('()=>Object.keys(Chart.instances).length')==8
                assert not errors,errors
            finally:
                browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()
