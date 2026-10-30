import json
import pytest
from db import db
from models import Proyecto,NucleusData,HistorialCambios
from services.rendicion_presupuesto_cotizacion import importe


@pytest.fixture
def escenarios(app,auth_client,monkeypatch):
    import blueprints.rendicion as flujo
    monkeypatch.setattr(flujo,'_avisar_flujo',lambda *a:None)
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        cp=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        records=[NucleusData(proyecto_id=cp,key_value='PRES-COT',data_json=json.dumps({'CLIENTE':'ENTEL','N° COTIZACION':'PRES-2026-001','SUB TOTAL + FEE':'1,000.00'}))]
        for key,state,amount,code,project in [
            ('PRES-ACTUAL','PENDIENTE','100.00','PRES-2026-001','Entel'),
            ('PRES-OTRA','VALIDADO','400','pres-2026-001','Entel'),
            ('PRES-PAGADA','DEPOSITADO','250','PRES-2026-001','Entel'),
            ('PRES-ANULADA','ANULADO','200','PRES-2026-001','Entel'),
            ('PRES-RECHAZADA','RECHAZADO','300','PRES-2026-001','Entel'),
            ('PRES-DIFERENTE','PENDIENTE','800','OTRA-COT','Entel'),
            ('PRES-OTRO-PROYECTO','VALIDADO','900','PRES-2026-001','Claro')]:
            records.append(NucleusData(proyecto_id=pid,key_value=key,data_json=json.dumps({'ESTADO':state,'Nombre del proyecto':project,'Monto total del depósito':amount,'N° COTIZACION':code,'Tipo de gasto':'VIÁTICOS','Tipo de presupuesto':'GASTO COBRA','MONTO PAGO':'50' if state=='DEPOSITADO' else ''})))
        db.session.add_all(records);db.session.commit();ids=[r.id for r in records]
    auth_client.get('/switch_project/'+str(pid))
    yield pid
    with app.app_context():
        HistorialCambios.query.filter(HistorialCambios.proyecto_id==pid,HistorialCambios.key_value.like('PRES-%')).delete(synchronize_session=False)
        NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()


def consulta(client,**extra):
    return client.get('/api/rendicion/cotizacion',query_string={'key':'PRES-ACTUAL','q':'PRES-2026-001',**extra})


def test_acumulado_no_duplica_actual_y_excluye_anulados(auth_client,escenarios):
    result=consulta(auth_client)
    assert result.status_code==200
    control=result.json['control']
    assert control['cotizado']=='1000.00'
    assert control['otras_solicitudes']=='650.00'
    assert control['solicitud_actual']=='100.00'
    assert control['acumulado']=='750.00' and control['saldo']=='250.00'
    assert control['cantidad_otras']==2 and control['excede'] is False
    excedido=consulta(auth_client,monto='400').json['control']
    assert excedido['excede'] is True and excedido['saldo']=='-50.00'


def test_busqueda_y_cotizacion_inexistente(auth_client,escenarios):
    result=consulta(auth_client,q='PRES-2026')
    assert result.json['opciones']==[{'numero':'PRES-2026-001'}]
    assert result.json['encontrada'] is False
    result=consulta(auth_client,q='NO-EXISTE')
    assert result.json['opciones']==[] and result.json['encontrada'] is False
    assert auth_client.get('/api/rendicion/cotizacion?key=NO-EXISTE&q=PRES').status_code==404


def test_validacion_guarda_presupuesto_asociacion_y_comparacion(app,auth_client,escenarios):
    response=auth_client.post('/api/rendicion/accion',json={'key':'PRES-ACTUAL','accion':'validar','tiempo':'No aplica','presupuesto':'800.00','cotizacion':'pres-2026-001'})
    assert response.status_code==200,response.json
    row=response.json['newData']
    assert row['PRESUPUESTO']=='800.00' and row['N° COTIZACION']=='PRES-2026-001'
    assert row['_COTIZACION_VINCULO']['id']
    assert row['_CONTROL_COTIZACION']['acumulado']=='750.00'
    assert row['ESTADO']=='VALIDADO'
    with app.app_context():
        stored=json.loads(NucleusData.query.filter_by(proyecto_id=escenarios,key_value='PRES-ACTUAL').one().data_json)
        assert stored['PRESUPUESTO']=='800.00'


def test_no_acepta_cotizacion_falsa_ni_monto_invalido(app,auth_client,escenarios):
    for payload in [{'presupuesto':'-1','cotizacion':''},{'presupuesto':'NaN','cotizacion':''},{'presupuesto':'100','cotizacion':'INEXISTENTE'}]:
        response=auth_client.post('/api/rendicion/accion',json={'key':'PRES-ACTUAL','accion':'validar','tiempo':'No aplica',**payload})
        assert response.status_code==400,response.json
    with app.app_context():
        stored=json.loads(NucleusData.query.filter_by(proyecto_id=escenarios,key_value='PRES-ACTUAL').one().data_json)
        assert stored['ESTADO']=='PENDIENTE' and 'PRESUPUESTO' not in stored


@pytest.mark.parametrize('raw,expected',[('1,234.56','1234.56'),('1.234,56','1234.56'),('25,50','25.50'),('0','0.00')])
def test_importes(raw,expected):assert str(importe(raw))==expected


from test_e2e_navegador import servidor


def test_formulario_busca_compara_y_guarda(app,auth_client,servidor,escenarios,tmp_path):
    from models import AppConfig
    from playwright.sync_api import sync_playwright,expect
    previous={}
    with app.app_context():
        for key,value in [('app_schema',['ESTADO','Tipo de presupuesto','Monto total del depósito']),('column_layout__validacion',[{'field':'ESTADO','visible':True},{'field':'Tipo de presupuesto','visible':True},{'field':'Monto total del depósito','visible':True}])]:
            cfg=AppConfig.query.filter_by(proyecto_id=escenarios,clave=key).first();previous[key]=cfg.valor if cfg else None
            if not cfg:cfg=AppConfig(proyecto_id=escenarios,clave=key);db.session.add(cfg)
            cfg.valor=json.dumps(value)
        db.session.commit()
    try:
        cookie=auth_client.get_cookie('session')
        with sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                context=browser.new_context(viewport={'width':1440,'height':1050})
                context.add_init_script("localStorage.setItem('nucleus-theme','dark')")
                context.add_cookies([{'name':'session','value':cookie.value,'domain':'127.0.0.1','path':'/'}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(servidor+'/',wait_until='networkidle')
                page.wait_for_function("typeof _rendFiltroFn==='function'")
                page.evaluate("rendValidar('PRES-ACTUAL')")
                selector=page.locator('select[data-rend-campo="Tipo de presupuesto"]')
                expect(selector).to_be_visible()
                assert selector.locator('option').all_text_contents()==['Seleccionar…','GASTO COBRA','REFACTURABLE']
                expect(page.locator('#rend-cotizacion-status')).to_contain_text('Dentro del monto cotizado')
                expect(page.locator('[data-rend-control="acumulado"]')).to_contain_text('750.00')
                page.locator('#rend-val-presupuesto').fill('800.00')
                selector.select_option('REFACTURABLE')
                page.locator('[data-rend-campo="Monto total del depósito"]').fill('400')
                expect(page.locator('#rend-cotizacion-status')).to_contain_text('Excede el monto cotizado')
                page.locator('#rend-correccion-save').click()
                expect(page.locator('#rend-correccion-status')).to_contain_text('Correcciones guardadas')
                expect(page.locator('#rend-val-presupuesto')).to_have_value('800.00')
                expect(page.locator('#rend-cotizacion-status')).to_contain_text('Excede el monto cotizado')
                page.locator('#rend-val-form').screenshot(path=str(tmp_path/'validacion-presupuesto.png'))
                page.locator('#rend-val-ops label').filter(has_text='No aplica').click()
                page.locator('#rend-modal-ok').click()
                page.wait_for_function("rawData.find(r=>r._key==='PRES-ACTUAL').ESTADO==='VALIDADO'")
                assert not errors,errors
            finally:browser.close()
        with app.app_context():
            row=json.loads(NucleusData.query.filter_by(proyecto_id=escenarios,key_value='PRES-ACTUAL').one().data_json)
            assert row['PRESUPUESTO']=='800.00' and row['Tipo de presupuesto']=='REFACTURABLE'
            assert row['_CONTROL_COTIZACION']['acumulado']=='1050.00'
            assert row['_CONTROL_COTIZACION']['excede'] is True
    finally:
        with app.app_context():
            for key,value in previous.items():
                cfg=AppConfig.query.filter_by(proyecto_id=escenarios,clave=key).one()
                if value is None:db.session.delete(cfg)
                else:cfg.valor=value
            db.session.commit()


def test_vinculo_por_id_cotizacion_mismo_proyecto(app,auth_client,escenarios):
    with app.app_context():
        cot=NucleusData.query.filter_by(key_value='PRES-COT').one()
        other=NucleusData.query.filter_by(proyecto_id=escenarios,key_value='PRES-OTRA').one()
        data=json.loads(other.data_json)
        data['N° COTIZACION']=''
        data['_COTIZACION_VINCULO']={'id':cot.id,'numero':'PRES-2026-001'}
        other.data_json=json.dumps(data);db.session.commit()
    assert consulta(auth_client).json['control']['otras_solicitudes']=='650.00'


def test_no_encuentra_cotizacion_de_otro_proyecto(app,auth_client,escenarios):
    with app.app_context():
        cot=NucleusData.query.filter_by(key_value='PRES-COT').one()
        data=json.loads(cot.data_json);data['CLIENTE']='CLARO';cot.data_json=json.dumps(data);db.session.commit()
    result=consulta(auth_client).json
    assert result['encontrada'] is False and result['opciones']==[]


def test_advertencia_monto_no_interpretable(app,auth_client,escenarios):
    with app.app_context():
        other=NucleusData.query.filter_by(proyecto_id=escenarios,key_value='PRES-OTRA').one()
        data=json.loads(other.data_json);data['Monto total del depósito']='sin monto';other.data_json=json.dumps(data);db.session.commit()
    assert consulta(auth_client).json['control']['importes_sin_interpretar']==1
