import json
from pathlib import Path
import pytest
pw=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from test_sustento_por_wo import caso
from test_sustento_flujo_completo import _prep
from test_cotizacion_proveedor import cotizacion
from db import db
from models import NucleusData,Proyecto


def browser_page(auth_client,p,servidor):
    browser=p.chromium.launch();context=browser.new_context(viewport={'width':1352,'height':950})
    cookie=auth_client.get_cookie('session');context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
    page=context.new_page();page.goto(servidor+'/',wait_until='networkidle');return browser,page


def test_cerrar_guarda_textos_y_fallo_no_los_descarta(app,auth_client,servidor,caso):
    _prep(app,caso,'WO-SUST-1');auth_client.get('/switch_project/%s'%caso['cot'])
    with pw.sync_playwright() as p:
        browser,page=browser_page(auth_client,p,servidor)
        try:
            page.evaluate("cotAbrirModalSustento('COT-SUST-TEST')")
            pw.expect(page.locator('#cot-ficha-expense')).to_be_visible()
            page.locator('#cot-ficha-expense').fill('EXP-CIERRE')
            page.locator('#evidencia-bitacora-inicio').fill('Texto conservado al cerrar')
            page.evaluate('cerrarWoModal()')
            pw.expect(page.locator('#modal-wo')).to_be_hidden()
            page.evaluate("cotAbrirModalSustento('COT-SUST-TEST')")
            pw.expect(page.locator('#cot-ficha-expense')).to_have_value('EXP-CIERRE')
            pw.expect(page.locator('#evidencia-bitacora-inicio')).to_have_value('Texto conservado al cerrar')
            page.locator('#cot-ficha-expense').fill('NO DESCARTAR')
            page.route('**/api/cotizacion/sustento/wo',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"Error temporal"}'))
            page.evaluate('cerrarWoModal()')
            pw.expect(page.locator('#modal-wo')).to_be_visible()
            pw.expect(page.locator('#cot-ficha-expense')).to_have_value('NO DESCARTAR')
        finally:browser.close()


def test_proveedor_seleccion_multiple_y_reabrir(auth_client,servidor,cotizacion):
    pid,key=cotizacion;auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion'});auth_client.get('/switch_project/%s'%pid)
    with pw.sync_playwright() as p:
        browser,page=browser_page(auth_client,p,servidor)
        try:
            page.evaluate("cotAbrirProveedor('TEST-PROVEEDOR')")
            # Una fila por factura; las órdenes de compra ya no se adjuntan aquí.
            for i,(factura,oc,subtotal) in enumerate([('F-1','OC-1','100'),('F-2','OC-2','23.50')]):
                if i:page.locator('#cot-prov-agregar').click()
                page.locator(f'#cot-prov-factura-{i}').fill(factura);page.locator(f'#cot-prov-oc-{i}').fill(oc);page.locator(f'#cot-prov-subtotal-{i}').fill(subtotal)
                with page.expect_file_chooser() as elegir:
                    page.locator('.cot-prov-fila').nth(i).locator('.cot-prov-subir').click()
                elegir.value.set_files({'name':f'factura-{i}.pdf','mimeType':'application/pdf','buffer':b'%PDF test'})
                pw.expect(page.locator('.cot-prov-fila').nth(i).locator('.cot-prov-doc')).to_have_count(1)
            pw.expect(page.locator('#cot-prov-total')).to_have_text('S/ 123.50')
            page.locator('#cot-proveedor-guardar').click()
            pw.expect(page.locator('#cot-proveedor-modal')).to_be_hidden()
            page.evaluate("cotAbrirProveedor('TEST-PROVEEDOR')")
            pw.expect(page.locator('.cot-prov-fila .cot-prov-doc')).to_have_count(2)
        finally:browser.close()


def test_claro_graficos_filtros_y_movil(app,auth_client,servidor,tmp_path):
    ids=[]
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        for n in range(36):
            d={'Ticket Id':'CM-DASH-'+str(n),'Task Type':'CM' if n%2 else 'PM','Task Status':'completed' if n%4 else 'inprocess','Create Time':f'2026-10-{n%28+1:02d} 08:00:00','Complete Time':f'2026-10-{n%28+2:02d} 20:00:00','Dispatch Time':f'2026-10-{n%28+1:02d} 09:00:00','SLA Status':'normal' if n%3 else 'sla_violation','FM Office':'CENTRO' if n%2 else 'SUR','Assign To FME Full Name':'Técnico '+str(n%3)}
            row=NucleusData(proyecto_id=pid,key_value=d['Ticket Id'],data_json=json.dumps(d));db.session.add(row);db.session.flush();ids.append(row.id)
        db.session.commit()
    try:
        with pw.sync_playwright() as p:
            browser,page=browser_page(auth_client,p,servidor)
            try:
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(servidor+'/analytics/claro',wait_until='networkidle')
                assert page.locator('canvas').count()==3
                assert page.locator('#cl-creados').inner_text()=='36'
                assert page.locator('#cl-despachados').inner_text()=='36'
                assert page.locator('#cl-cancelados').inner_text()=='0'
                page.locator('#cl-zona').select_option('CENTRO');pw.expect(page.locator('#cl-creados')).to_have_text('18')
                page.locator('[data-scale=semana]').click();page.locator('#cl-limpiar').click()
                page.locator('[data-scale=dia]').click()
                for width in (1352,390):
                    page.set_viewport_size({'width':width,'height':950});page.evaluate('document.body.classList.add("dark-mode")')
                    assert page.locator('.dc-page').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                    page.screenshot(path=str(tmp_path/f'claro-{width}.png'),full_page=True)
                assert not errors,errors
            finally:browser.close()
    finally:
        with app.app_context():NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()
