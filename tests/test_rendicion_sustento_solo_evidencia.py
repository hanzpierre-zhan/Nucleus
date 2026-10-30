"""Segundo formulario: fuera de grilla/exportables, disponible en Evidencia."""
import json
import pytest
from db import db
from models import Proyecto,AppConfig,NucleusData
from test_e2e_navegador import servidor
pw=pytest.importorskip('playwright.sync_api')


def test_sustento_solo_en_evidencia(app,auth_client,servidor):
    key='SUSTENTO-SOLO-EVIDENCIA-TEST';previous={}
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        data={'ESTADO':'CON SUSTENTO','Nombre del proyecto':'Claro','MONTO PAGO':'50',
              'SUSTENTO_PRECIO COMPRAS':'SUSTENTO-DETALLE-123',
              'SUSTENTO_FOTO COMPRAS':'/static/img/brand-symbol.svg'}
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
                page.evaluate('toggleVisibilityMenu()')
                assert 'SUSTENTO_' not in page.locator('#col-list').inner_text()
                page.evaluate("Object.defineProperty(navigator.clipboard,'writeText',{value:async t=>{window.copiedTest=t},configurable:true});copiarRendicionTSV()")
                assert 'SUSTENTO_' not in page.evaluate('window.copiedTest.split(\'\\n\')[0]')
                assert 'SUSTENTO-DETALLE-123' not in page.evaluate('window.copiedTest')
                headers=page.evaluate("(()=>{let headers;const old=XLSX.writeFile;XLSX.writeFile=wb=>{headers=XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]],{header:1})[0]};try{descargarExcel()}finally{XLSX.writeFile=old}return headers})()")
                assert headers and not any(str(h).startswith('SUSTENTO_') for h in headers)
                page.evaluate('(key)=>rendAbrirDetalleEvidencia(key)',key)
                pw.expect(page.locator('#evidencia-contenedor')).to_contain_text('SUSTENTO-DETALLE-123')
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
