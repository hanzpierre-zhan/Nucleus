import json
import pytest
playwright_api=pytest.importorskip('playwright.sync_api')
from test_e2e_navegador import servidor
from test_sustento_por_wo import caso,foto
from db import db
from models import NucleusData


def test_ficha_ampliada_guarda_y_restaura_modal(app,auth_client,servidor,caso,monkeypatch,tmp_path):
    import blueprints.cotizacion as cot
    monkeypatch.setattr(cot,'evidencia_usa_b2',lambda:False)
    monkeypatch.setattr(cot,'_ubicacion_folder',lambda cid:str(tmp_path/str(cid)))
    with app.app_context():
        fila=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(fila.data_json);d.update({'ITEMS_JSON':json.dumps([{'correlativo':'1','texto':'Compra de cable AWS 2x12 (100 metros)','tipo':'REEMBOLSABLE','und':'UI','cantidad':'1'},{'correlativo':'2','texto':'Acarreo de cable de ida y vuelta al sitio','tipo':'REEMBOLSABLE','und':'UI','cantidad':'2'},{'correlativo':'3','texto':'Pago por derecho de consumo de energía','tipo':'REEMBOLSABLE','und':'UI','cantidad':'1'}]),'NOMBRE SITE':'013304_CS_Ollantaytambo','CODIGO SITE':'013304','REGION':'Cusco','DISTRITO':'Ollantaytambo','PROVINCIA':'Urubamba'});fila.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/%s'%caso['cot']);cookie=auth_client.get_cookie('session')
    with playwright_api.sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            context=browser.new_context(viewport={'width':1600,'height':1100})
            context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(servidor+'/',wait_until='networkidle')
            page.evaluate('document.body.classList.add("dark-mode")')
            page.evaluate("cotAbrirModalSustento('COT-SUST-TEST')")
            playwright_api.expect(page.locator('#cot-sustento-ficha')).to_be_visible()
            assert page.locator('#cot-ficha-wo').input_value()=='WO-SUST-1'
            assert page.locator('#cot-ficha-quotation_number').input_value()=='COT-SUST-TEST'
            assert page.locator('#cot-ficha-quotation_number').get_attribute('readonly') is not None
            assert page.locator('#cot-sustento-wo-tabs').count()==0
            assert page.locator('#cot-btn-guardar-sustento').count()==0
            assert not page.locator('#btn-wo-copiar').is_visible()
            assert page.locator('#cot-btn-generar-expediente').is_enabled()
            assert page.get_by_role('button',name='Agregar o quitar responsables del trabajo').count()==1
            page.get_by_role('button',name='Agregar o quitar responsables del trabajo').click()
            dialog=page.locator('.manual-options-dialog')
            dialog.get_by_role('button',name='+ Agregar opción').click()
            dialog.get_by_role('textbox',name='Opción').last.fill('Responsable del catálogo')
            dialog.get_by_role('button',name='Guardar opciones').click()
            playwright_api.expect(page.locator('#cot-work-responsibles option[value="Responsable del catálogo"]')).to_have_count(1)
            assert page.locator('#cot-sustento-items .cot-item-card').count()==3
            assert page.locator('.cot-item-phase').count()==9
            assert page.locator('.cot-sustento-title').inner_text()=='Sustento de la cotización'
            assert not page.locator('#wo-tab-evidencia').is_visible()
            assert not page.locator('#btn-evidencia-zip').is_visible()
            assert page.locator('#cot-ficha-site_id').input_value()=='013304'
            for key in ('site_name','site_id','site_address','site_type','district','province','region'):
                assert page.locator('#cot-ficha-'+key).get_attribute('list')=='cot-ficha-options-'+key
            page.locator('#cot-ficha-site_id').fill('LI2066')
            playwright_api.expect(page.locator('#cot-ficha-site_name')).to_have_value('EB ZARATE')
            assert page.locator('#cot-ficha-district').input_value()=='SAN JUAN DE LURIGANCHO'
            assert page.locator('#cot-ficha-region').input_value()=='LIMA ESTE'
            assert page.locator('#evidencia-bitacora-inicio').input_value()=='Comentario WO 1'
            assert page.locator('.cot-ficha-texts textarea').count()==3
            assert page.locator('#modal-wo .wo-modal').bounding_box()['width']<=850
            page.locator('#cot-ficha-ajb_ejb').fill('AJB-2026-045')
            page.locator('#cot-ficha-expense').fill('EXP-2026-028')
            page.locator('#cot-ficha-work_responsible').fill('Responsable de prueba')
            assert page.locator('label[for=wo-inicio-ejecucion]').inner_text()=='Fecha de inicio | Start date'
            assert page.locator('label[for=wo-fin-ejecucion]').inner_text()=='Fecha de fin | End date'
            page.locator('#cot-ficha-site_type').fill('Rooftop')
            page.locator('#cot-ficha-site_address').fill('Av. Principal, Ollantaytambo, Cusco')
            page.locator('#evidencia-bitacora-inicio').fill('Se identificaron fallas de energía en el sitio durante la inspección inicial.')
            page.locator('#evidencia-bitacora-proceso').fill('Restablecer la continuidad del servicio y verificar las condiciones de operación.')
            page.locator('#evidencia-bitacora-cierre').fill('Se realizaron las verificaciones y los trabajos de mantenimiento correspondientes.')
            page.locator('#cot-ficha-wo').scroll_into_view_if_needed()
            page.screenshot(path=str(tmp_path/'vista-previa.png'))
            page.locator('#cot-ficha-site_name').fill('Sitio manual prueba')
            page.locator('#cot-ficha-site_id').fill('MANUAL-001')
            assert page.locator('#cot-ficha-site_name').input_value()=='Sitio manual prueba'
            page.locator('.cot-ficha-picture input').set_input_files({'name':'ubicacion.png','mimeType':'image/png','buffer':foto().read()})
            playwright_api.expect(page.locator('.cot-ficha-location .cot-ficha-status')).to_contain_text('Foto guardada')
            first=page.locator('.cot-item-card').first
            assert not first.evaluate('(e)=>e.open')
            first.locator('summary').click()
            assert first.locator('[data-item-field=quantity]').count()==0
            assert first.locator('[data-item-field=remarks]').input_value()==''
            heights=first.evaluate('(e)=>[...e.querySelectorAll("select, textarea")].map(n=>n.getBoundingClientRect().height)')
            assert max(heights)-min(heights)<2
            assert first.locator('[data-item-field=unique_code]').input_value()=='8828126757'
            assert first.locator('[data-item-field=unit]').input_value()=='EACH'
            first.locator('[data-item-field=unique_code]').select_option('8828126700')
            assert first.locator('[data-item-field=unit]').input_value()=='DAY'
            assert 'Alquiler' in first.locator('[data-item-field=description_es]').input_value()
            assert first.locator('[data-item-field=activity]').input_value()==first.locator('[data-item-field=description_es]').input_value()
            first.locator('[data-item-field=description_en]').fill('Purchase of cable')
            first.locator('[data-item-field=activity]').fill('Cable delivery and installation')
            first.locator('[data-item-field=remarks]').fill('Revisar con el supervisor')
            first.locator('[data-phase=before] .cot-item-upload input').set_input_files({'name':'item-uno.png','mimeType':'image/png','buffer':foto().read()})
            playwright_api.expect(first.locator('.cot-ficha-status')).to_have_text('Fotos guardadas.')
            assert first.locator('.cot-item-photo').count()==1
            first.locator('[data-phase=before] input[multiple]').set_input_files([{'name':'extra-uno.png','mimeType':'image/png','buffer':foto().read()},{'name':'extra-dos.png','mimeType':'image/png','buffer':foto().read()}])
            playwright_api.expect(first.locator('.cot-item-photo')).to_have_count(3)
            for phase in ('during','after'):
                first.locator(f'[data-phase={phase}] input[multiple]').set_input_files({'name':phase+'.png','mimeType':'image/png','buffer':foto().read()})
                playwright_api.expect(first.locator(f'[data-phase={phase}] .cot-item-photo')).to_have_count(1)
            with page.expect_download() as generated:
                page.locator('#cot-btn-generar-expediente').click()
            download=generated.value
            download.save_as(str(tmp_path/'expediente-desde-boton.xlsx'))
            from openpyxl import load_workbook
            report=load_workbook(str(tmp_path/'expediente-desde-boton.xlsx'))
            assert report['Información general']['K5'].value=='Responsable de prueba'
            assert report['Carátula']['E45'].value=='COT-SUST-TEST'
            assert len(report['Partidas']._images)==5
            saved=page.evaluate('cotGuardarSustentoSeleccionado(false)')
            assert saved['success'] and saved['wo_data']['_SUSTENTO_MANUAL']['expense']=='EXP-2026-028'
            assert saved['wo_data']['_SUSTENTO_MANUAL']['site_name']=='Sitio manual prueba'
            assert saved['wo_data']['_SUSTENTO_MANUAL']['site_id']=='MANUAL-001'
            page.evaluate("cerrarWoModal();cotAbrirModalSustento('COT-SUST-TEST')")
            playwright_api.expect(page.locator('#cot-ficha-expense')).to_have_value('EXP-2026-028')
            playwright_api.expect(page.locator('.cot-item-card').first.locator('[data-phase=before] .cot-item-photo')).to_have_count(3)
            for phase in ('during','after'):
                assert page.locator('.cot-item-card').first.locator(f'[data-phase={phase}] .cot-item-photo').count()==1
            first=page.locator('.cot-item-card').first
            assert not first.evaluate('(e)=>e.open')
            first.locator('summary').click()
            assert first.locator('[data-item-field=unique_code]').input_value()=='8828126700'
            assert first.locator('[data-item-field=description_en]').input_value()=='Purchase of cable'
            assert first.locator('[data-item-field=activity]').input_value()=='Cable delivery and installation'
            assert first.locator('[data-item-field=remarks]').input_value()=='Revisar con el supervisor'
            assert page.locator('#cot-ficha-work_responsible').input_value()=='Responsable de prueba'
            for width in (1600,390):
                page.set_viewport_size({'width':width,'height':1100 if width==1600 else 844})
                assert page.locator('#cot-sustento-ficha').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                page.locator('#cot-ficha-wo').scroll_into_view_if_needed()
                page.screenshot(path=str(tmp_path/f'ficha-{width}.png'))
                page.locator('#evidencia-bitacora-proceso').scroll_into_view_if_needed()
                page.screenshot(path=str(tmp_path/f'descripcion-{width}.png'))
                page.locator('#cot-sustento-items').scroll_into_view_if_needed()
                page.screenshot(path=str(tmp_path/f'items-{width}.png'))
            page.evaluate('cerrarWoModal()')
            assert page.locator('#cot-sustento-ficha').count()==0
            assert page.locator('#cot-ficha-work_responsible').count()==0
            assert page.locator('#evidencia-inicio-proceso-cierre #evidencia-bitacora-inicio').count()==1
            with app.app_context():
                cot_row=db.session.get(NucleusData,caso['ids'][2]);cot_data=json.loads(cot_row.data_json);cot_data['CLIENTE']='PEXT';cot_row.data_json=json.dumps(cot_data);db.session.commit()
            page.evaluate("cotAbrirModalSustento('COT-SUST-TEST')")
            playwright_api.expect(page.locator('#wo-tab-evidencia')).to_be_visible()
            assert page.locator('#cot-sustento-ficha').count()==0
            assert page.locator('#cot-btn-guardar-sustento').is_visible()
            assert page.locator('#cot-sustento-items').count()==0
            from models import Proyecto
            from services.sites_general import EXCEL_KEYS
            with app.app_context():site_id=Proyecto.query.filter_by(nombre='SITE').one().id
            page.set_viewport_size({'width':1600,'height':1100})
            page.goto(servidor+'/switch_project/'+str(site_id),wait_until='networkidle')
            titles=page.locator('.tabulator-header .tabulator-col-title').all_text_contents()
            titles=[title.strip() for title in titles if title.strip()]
            assert titles==EXCEL_KEYS,titles
            page.screenshot(path=str(tmp_path/'sites-columnas-excel.png'))
            assert not errors,errors
        finally:browser.close()
