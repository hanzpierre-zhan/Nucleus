"""Segundo formulario: fuera de grilla/exportables, disponible en Evidencia."""
import json
import pytest
from db import db
from models import Proyecto,AppConfig,NucleusData
from test_e2e_navegador import servidor
pw=pytest.importorskip('playwright.sync_api')


def test_sustento_solo_en_evidencia(app,auth_client,servidor,tmp_path):
    key='SUSTENTO-SOLO-EVIDENCIA-TEST';previous={}
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        data={'ESTADO':'CON SUSTENTO','Nombre del proyecto':'Claro','MONTO PAGO':'50',
              'SUSTENTO_PRECIO COMPRAS':'12.50',
              'SUSTENTO_FOTO COMPRAS':'/static/img/brand-symbol.svg',
              'FOTO PAGO':'/static/img/brand-symbol.svg?pago=1',
              'SUSTENTO_DOCUMENTO':'00123456','SUSTENTO_MOTO TOTAL DE LO GASTADO':'50',
              'SUSTENTO_ADJUNTAR COMPROBANTE':'/static/documento.pdf, /static/reporte.docx',
              'SUSTENTO_PRECIO PEAJE':'7.80','SUSTENTO_RUC PEAJE':'20517252558',
              'SUSTENTO_TIPO DOCUMENTO PEAJE':'Factura',
              'SUSTENTO_FOTO PEAJE':'/static/img/brand-symbol.svg?peaje=1, /static/img/brand-symbol.svg?peaje=2',
              'SUSTENTO_CARGAR EVIDENCIAS':'/static/img/brand-symbol.svg?trabajo=1, /static/img/brand-symbol.svg?trabajo=2, /static/img/brand-symbol.svg?trabajo=3',
              'Cruce de personal':'Verificado','DEPARTAMENTO':'Lima',
              'Documento del beneficiario':'00123456','Documento del beneficiario (Form)':'00123456',
              'CODIGO DEPOSITO':'COB-TEST','ESTADO (Form)':'EXTERNO',
              'CODIGO DEPOSITO (Form)':'EXTERNO','MONTO PAGO (Form)':'999'}
        db.session.add(NucleusData(proyecto_id=pid,key_value=key,data_json=json.dumps(data)))
        for name,value in [('app_schema',list(data)),('column_layout__validacion',[{'field':'SUSTENTO_PRECIO COMPRAS','visible':True},{'field':'ESTADO','visible':True}])]:
            cfg=AppConfig.query.filter_by(proyecto_id=pid,clave=name).first();previous[name]=cfg.valor if cfg else None
            if not cfg:cfg=AppConfig(proyecto_id=pid,clave=name);db.session.add(cfg)
            cfg.valor=json.dumps(value)
        db.session.commit()
    try:
        auth_client.get('/switch_project/'+str(pid));cookie=auth_client.get_cookie('session')
        with pw.sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                context=browser.new_context(viewport={'width':1500,'height':900})
                context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
                page=context.new_page();page.goto(servidor+'/',wait_until='networkidle')
                page.wait_for_function("typeof _rendFiltroFn==='function'")
                assert page.evaluate("table.getColumns().every(c=>!String(c.getField()).startsWith('SUSTENTO_'))")
                excluded=['Cruce de personal','DEPARTAMENTO','Documento del beneficiario',
                          'ESTADO (Form)','CODIGO DEPOSITO (Form)','MONTO PAGO (Form)']
                assert page.evaluate('(fields)=>fields.every(f=>!table.getColumn(f))',excluded)
                assert page.evaluate('Boolean(table.getColumn("Documento del beneficiario (Form)"))')
                assert page.locator('.tabulator-col[tabulator-field="Documento del beneficiario (Form)"]').inner_text().startswith('F1.')
                page.evaluate('toggleVisibilityMenu()')
                assert 'SUSTENTO_' not in page.locator('#col-list').inner_text()
                page.evaluate("Object.defineProperty(navigator.clipboard,'writeText',{value:async t=>{window.copiedTest=t},configurable:true});copiarRendicionTSV()")
                assert 'SUSTENTO_' not in page.evaluate('window.copiedTest.split(\'\\n\')[0]')
                assert '12.50' not in page.evaluate('window.copiedTest')
                copied=page.evaluate('window.copiedTest').splitlines()
                assert copied[1].split('\t')[copied[0].split('\t').index('ESTADO')]=='4.CON SUSTENTO'
                exported=page.evaluate("(()=>{let rows;const old=XLSX.writeFile;XLSX.writeFile=wb=>{rows=XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]],{header:1})};try{descargarExcel()}finally{XLSX.writeFile=old}return rows})()")
                assert exported[1][exported[0].index('ESTADO')]=='4.CON SUSTENTO'
                assert page.evaluate('(key)=>rawData.find(r=>r._key===key).ESTADO',key)=='CON SUSTENTO'
                headers=page.evaluate("(()=>{let headers;const old=XLSX.writeFile;XLSX.writeFile=wb=>{headers=XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]],{header:1})[0]};try{descargarExcel()}finally{XLSX.writeFile=old}return headers})()")
                assert headers and not any(str(h).startswith('SUSTENTO_') for h in headers)
                assert not any(f in headers for f in excluded)
                assert 'F1. Documento del beneficiario (Form)' in headers
                assert all(f in headers for f in ['ESTADO','Código depósito','MONTO PAGO'])
                tsv_headers=page.evaluate('window.copiedTest').splitlines()[0].split('\t')
                assert not any(f in tsv_headers for f in excluded)
                assert 'F1. Documento del beneficiario (Form)' in tsv_headers
                page.evaluate('toggleVisibilityMenu()')
                page.evaluate('(key)=>rendAbrirDetalleEvidencia(key)',key)
                pw.expect(page.locator('#evidencia-contenedor')).to_contain_text('12.50')
                pw.expect(page.locator('#evidencia-contenedor')).to_contain_text('F2. PRECIO COMPRAS')
                assert page.locator('.ev-trabajo .ev-f').count()==3
                assert page.locator('.ev-comprobantes .ev-f').count()==6
                assert page.locator('.ev-comprobantes-grid > .ev-card').first.get_attribute('data-cat')=='GENERAL'
                assert page.locator('.ev-card[data-cat="GENERAL"] img').get_attribute('src').endswith('?pago=1')
                assert page.locator('#ev-stats').count()==0
                assert page.locator('.ev-card[data-cat="PAGO"]').count()==0
                assert page.locator('.ev-section-title').count()==0
                pw.expect(page.locator('.ev-file-link').first).to_contain_text('Adjunto · PDF')
                pw.expect(page.locator('.ev-file-link').last).to_contain_text('Adjunto · Word')
                assert page.evaluate("EV_FOTOS.length") == 7
                for width in [1500,390]:
                    page.set_viewport_size({'width':width,'height':950})
                    photos=page.locator('.ev-card[data-cat="PEAJE"] .ev-f-wrap')
                    assert abs(photos.nth(0).bounding_box()['y']-photos.nth(1).bounding_box()['y'])<4
                    assert page.locator('.ev-card[data-cat="PEAJE"] .ev-t').first.evaluate('(el)=>getComputedStyle(el).flexDirection')=='row'
                    top=page.locator('.ev-comprobantes').bounding_box()
                    work=page.locator('.ev-trabajo').bounding_box()
                    assert work['y'] >= top['y'] + top['height'] - 1
                    assert page.locator('.ev-modal').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                    page.screenshot(path=str(tmp_path / ('evidencia-' + str(width) + '.png')))
                page.set_viewport_size({'width':1500,'height':950})
                assert page.locator('.ev-trabajo').is_visible()
                page.locator('.ev-trabajo .ev-f').first.click()
                assert page.locator('.ev-lb').is_visible()
                page.keyboard.press('Escape')
                assert page.locator('.ev-comprobantes').is_visible()
                assert page.locator('#evidencia-contenedor img').count()>0
                assert page.evaluate('(key)=>rawData.find(r=>r._key===key)["SUSTENTO_FOTO COMPRAS"]',key)=='/static/img/brand-symbol.svg'
            finally:browser.close()
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid,key_value=key).delete()
            for name,value in previous.items():
                cfg=AppConfig.query.filter_by(proyecto_id=pid,clave=name).one()
                if value is None:db.session.delete(cfg)
                else:cfg.valor=value
            db.session.commit()
