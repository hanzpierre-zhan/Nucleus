import json
import pytest
playwright_api=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from db import db
from models import Proyecto,NucleusData


def test_grafico_y_filtro_conservan_identidad_por_dni(app,auth_client,servidor):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        ids=[]
        for n,(doc,name,amount) in enumerate([('00123456','Juan Perez',100),('00123456','J. Perez',50),('87654321','Juan Perez',20)]):
            row=NucleusData(proyecto_id=pid,key_value='BENEF-QA-'+str(n),data_json=json.dumps({
                'Nombre del proyecto':'ENTEL','Documento del beneficiario':doc,'Técnico beneficiario':name,
                'ESTADO':'DEPOSITADO','MONTO PAGO':str(amount),'Marca temporal':'2026-10-01','FECHA PAGO':'2026-10-02'
            }))
            db.session.add(row);db.session.flush();ids.append(row.id)
        db.session.commit()
    try:
        cookie=auth_client.get_cookie('session')
        with playwright_api.sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                context=browser.new_context()
                context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(servidor+'/analytics/rendicion',wait_until='networkidle')
                page.wait_for_function('window.Chart && Chart.getChart("re-entel")')
                options=page.locator('#df-person option').evaluate_all('(nodes)=>nodes.map(n=>({value:n.value,text:n.textContent}))')
                assert any(o['value']=='dni:00123456' and o['text']=='J. Perez' for o in options)
                assert any(o['value']=='dni:87654321' and o['text']=='Juan Perez' for o in options)
                data=page.evaluate('()=>{const c=Chart.getChart("re-entel");return {labels:c.data.labels,values:c.data.datasets[0].data}}')
                assert 150 in data['values'] and 20 in data['values']
                assert all('00123456' not in str(label) for label in data['labels'])
                page.locator('#df-person').select_option('dni:00123456')
                assert page.evaluate('()=>Chart.getChart("re-entel").data.datasets[0].data') == [150]
                playwright_api.expect(page.locator('#df-caption')).to_contain_text('2 registros')
                assert not errors,errors
            finally:
                browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()
