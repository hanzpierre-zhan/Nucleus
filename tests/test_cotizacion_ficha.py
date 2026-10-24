import io,json
from PIL import Image
from db import db
from models import NucleusData,Proyecto
from test_sustento_por_wo import caso,cargar,foto


def test_ficha_y_wo_definida_conservan_fuente_y_fotos(app,auth_client,caso):
    auth_client.get('/switch_project/%s'%caso['cot'])
    carga=cargar(auth_client,caso);assert carga.status_code==200
    manual={'wo':'WO-DEFINITIVA','ajb_ejb':'AJB-45','expense':'EXP-10','site_name':'Sitio final','site_id':'S-001','site_address':'Av. Principal 100','site_type':'Rooftop','district':'Miraflores','province':'Lima','region':'Lima'}
    r=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':manual,'evidencia':{'_BITACORA_INICIO':'Antecedentes nuevos'}})
    assert r.status_code==200,r.json
    assert r.json['newData']['NUMERO WO']=='WO-DEFINITIVA, WO-SUST-2'
    wos=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos']
    assert wos[0]['wo_data']['_SUSTENTO_MANUAL']['site_id']=='S-001'
    assert wos[0]['wo_data']['_BITACORA_INICIO']=='Antecedentes nuevos'
    assert wos[0]['fotos_urls']['inicio']==[carga.json['url']]
    assert auth_client.get(carga.json['url']).status_code==200
    with app.app_context():
        assert db.session.get(NucleusData,caso['ids'][0]).key_value=='WO-SUST-1'
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-DEFINITIVA','manual':{'wo':'WO-SUST-2'}}).status_code==400
    assert auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'COT-SUST-TEST','wo':'WO-DEFINITIVA'}).status_code==200
    aprobacion=auth_client.post('/api/cotizacion/accion',json={'key':'COT-SUST-TEST','accion':'aprobar_sustento'})
    assert aprobacion.status_code==200,aprobacion.json
    registros=auth_client.get('/refacturable/api/registros').json
    if isinstance(registros,dict):registros=registros.get('registros',[])
    liquidacion=next(r for r in registros if r['cotizacion']=='COT-SUST-TEST')
    assert carga.json['url'] in liquidacion['fotos']['inicio']


def test_agregar_y_quitar_wo_sin_perder_descripcion(app,auth_client,caso):
    with app.app_context():
        cot=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(cot.data_json);d['NUMERO WO']='';d['_BITACORA_INICIO']='Texto anterior';cot.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/%s'%caso['cot'])
    for old,new in [('', 'NUEVA-123'),('NUEVA-123','')]:
        r=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':old,'manual':{'wo':new,'site_name':'Sitio','site_id':'123'}})
        assert r.status_code==200,r.json
        assert r.json['newData']['NUMERO WO']==new
        wos=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos']
        assert wos[0]['wo_data']['_BITACORA_INICIO']=='Texto anterior'
        assert wos[0]['wo_data']['_SUSTENTO_MANUAL']['wo']==new


def test_foto_ubicacion_se_conserva_y_respeta_bloqueos(app,auth_client,caso,monkeypatch,tmp_path):
    import blueprints.cotizacion as cot
    monkeypatch.setattr(cot,'evidencia_usa_b2',lambda:False)
    monkeypatch.setattr(cot,'_ubicacion_folder',lambda cid:str(tmp_path/str(cid)))
    auth_client.get('/switch_project/%s'%caso['cot'])
    r=auth_client.post('/api/cotizacion/sustento/ubicacion',data={'key':'COT-SUST-TEST','wo':'WO-SUST-1','foto':(foto(),'ubicacion.png')})
    assert r.status_code==200,r.json
    assert auth_client.get(r.json['url']).status_code==200
    result=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':{'wo':'WO-FINAL'}})
    assert result.status_code==200,result.json
    assert result.json['wo_data']['_SUSTENTO_MANUAL']['location_picture']==r.json['url']
    assert auth_client.get(r.json['url']).status_code==200
    assert auth_client.post('/api/cotizacion/sustento/ubicacion',data={'key':'COT-SUST-TEST','wo':'OTRA','foto':(foto(),'foto.png')}).status_code==400
    with app.app_context():
        fila=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(fila.data_json);d['_SUSTENTO_APROBADO']='1';fila.data_json=json.dumps(d);db.session.commit()
    assert auth_client.post('/api/cotizacion/sustento/ubicacion',data={'key':'COT-SUST-TEST','wo':'WO-FINAL','foto':(foto(),'foto.png')}).status_code==403
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-FINAL','manual':{'expense':'X'}}).status_code==403


def test_catalogo_devuelve_nombre_y_codigo_juntos(app,auth_client,caso):
    with app.app_context():
        p=Proyecto.query.filter_by(nombre='SITE').first()
        if not p:p=Proyecto(nombre='SITE');db.session.add(p);db.session.flush()
        f=NucleusData(proyecto_id=p.id,key_value='SITE-FICHA-1',data_json=json.dumps({'Nombre':'Sitio de prueba ficha','Código':'CL-123','Dirección':'Av. Lima','Distrito':'Surco','Provincia':'Lima','Región':'Lima'}));db.session.add(f);db.session.commit();fid=f.id
    try:
        auth_client.get('/switch_project/%s'%caso['cot'])
        for q in ('prueba ficha','CL-123'):
            r=auth_client.get('/api/cotizacion/sustento/sites',query_string={'q':q})
            assert r.status_code==200
            site=next(s for s in r.json['sites'] if s['site_id']=='CL-123')
            assert site['site_name']=='Sitio de prueba ficha' and site['district']=='Surco'
    finally:
        with app.app_context():NucleusData.query.filter_by(id=fid).delete();db.session.commit()


def test_fotos_por_item_sin_limite_de_cinco_y_sin_mezclar(app,auth_client,caso,monkeypatch,tmp_path):
    import blueprints.cotizacion as cot
    monkeypatch.setattr(cot,'evidencia_usa_b2',lambda:False)
    monkeypatch.setattr(cot,'_ubicacion_folder',lambda cid:str(tmp_path/str(cid)))
    items=[{'correlativo':'1','texto':'Compra de cable','tipo':'REEMBOLSABLE','und':'UI','cantidad':'1'},
           {'correlativo':'2','texto':'Acarreo del cable','tipo':'REEMBOLSABLE','und':'UI','cantidad':'2'}]
    with app.app_context():
        fila=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(fila.data_json);d['ITEMS_JSON']=json.dumps(items);d['N° COTIZACION']='HW-2026-000345';fila.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/%s'%caso['cot'])
    source=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json
    first,second=source['items'];urls=[]
    for n in range(6):
        r=auth_client.post('/api/cotizacion/sustento/item-foto',data={'key':'COT-SUST-TEST','wo':'WO-SUST-1','item_key':first['key'],'foto':(foto(),f'foto-{n}.png')})
        assert r.status_code==200,r.json
        urls.append(r.json['url']);assert len(r.json['photos'])==n+1
    r=auth_client.post('/api/cotizacion/sustento/item-foto',data={'key':'COT-SUST-TEST','wo':'WO-SUST-1','item_key':second['key'],'foto':(foto(),'segundo.png')})
    assert r.status_code==200 and len(r.json['photos'])==1
    assert auth_client.get(urls[0]).status_code==200
    invalid=auth_client.post('/api/cotizacion/sustento/item-foto',data={'key':'COT-SUST-TEST','wo':'WO-SUST-1','item_key':'ajeno','foto':(foto(),'otro.png')})
    assert invalid.status_code==400
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':{'quotation_number':'CAMBIADA'}}).status_code==400
    saved=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':{'expense':'Prueba'}})
    assert saved.status_code==200 and saved.json['newData']['N° COTIZACION']=='HW-2026-000345'
    assert saved.json['newData']['ESTADO COTIZACION']=='Aprobado'
    with app.app_context():
        fila=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(fila.data_json);items.reverse();items[1]['cantidad']='9';d['ITEMS_JSON']=json.dumps(items);fila.data_json=json.dumps(d);db.session.commit()
    source=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json
    assert source['items'][1]['key']==first['key']
    photos=source['wos'][0]['wo_data']['_SUSTENTO_MANUAL']['item_photos']
    assert len(photos[first['key']])==6 and len(photos[second['key']])==1
    assert not source['wos'][1]['wo_data']['_SUSTENTO_MANUAL'].get('item_photos')


def test_campos_manuales_de_item_se_guardan_sin_cambiar_cotizacion(app,auth_client,caso):
    with app.app_context():
        row=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(row.data_json)
        original=[{'correlativo':'1','texto':'Instalación de cable','tipo':'LPU','cantidad':'2','und':'m'}]
        d['ITEMS_JSON']=json.dumps(original);row.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/%s'%caso['cot'])
    key=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['items'][0]['key']
    fields={'unique_code':'LPU-10','quantity':'2,5','unit':'m','description_es':'Partida ajustada','description_en':'Cable installation','activity':'Instalar y verificar cableado'}
    saved=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':{'item_details':{key:fields}}})
    assert saved.status_code==200,saved.json
    assert json.loads(saved.json['newData']['ITEMS_JSON'])==original
    current=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos']
    assert current[0]['wo_data']['_SUSTENTO_MANUAL']['item_details'][key]==fields
    assert not current[1]['wo_data']['_SUSTENTO_MANUAL'].get('item_details')
    for invalid in ({'otro':fields},{key:{'quantity':'-1'}},{key:{'quantity':'NaN'}},{key:{'campo_inventado':'X'}}):
        response=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':{'item_details':invalid}})
        assert response.status_code==400,response.json


def test_pext_conserva_sustento_anterior(app,auth_client,caso):
    with app.app_context():
        row=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(row.data_json);d['CLIENTE']='PEXT';row.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/%s'%caso['cot'])
    r=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST');assert r.json['lpu']==[]
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','manual':{'expense':'No aplicar'}}).status_code==400
    r=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','evidencia':{'_BITACORA_INICIO':'Texto PEXT'}})
    assert r.status_code==200,r.json
