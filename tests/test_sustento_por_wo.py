import io,json
import pytest
from PIL import Image
from db import db
from models import Proyecto,NucleusData

@pytest.fixture
def caso(app,monkeypatch,tmp_path):
    import blueprints.evidencia as ev
    monkeypatch.setattr(ev,'evidencia_usa_b2',lambda:False)
    monkeypatch.setattr(ev,'onedrive_subir',lambda *a:None)
    monkeypatch.setattr(ev,'onedrive_eliminar',lambda *a:None)
    with app.app_context():
        flm=Proyecto.query.filter_by(nombre='FLM - CLARO').one();cot=Proyecto.query.filter_by(nombre='Cotizaciones').one()
        filas=[]
        for n in (1,2):
            f=NucleusData(proyecto_id=flm.id,key_value='WO-SUST-'+str(n),data_json=json.dumps({'_BITACORA_INICIO':'Comentario WO '+str(n)}));db.session.add(f);filas.append(f)
        f=NucleusData(proyecto_id=cot.id,key_value='COT-SUST-TEST',data_json=json.dumps({'CLIENTE':'CLARO','ESTADO COTIZACION':'Aprobado','NUMERO WO':'WO-SUST-1, WO-SUST-2'}));db.session.add(f);filas.append(f);db.session.commit();ids=[f.id for f in filas]
        datos={'flm':flm.id,'cot':cot.id,'ids':ids}
    yield datos
    with app.app_context():
        NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()


def foto():
    b=io.BytesIO();Image.new('RGB',(16,16),'blue').save(b,format='PNG');b.seek(0);return b


def cargar(client,caso):
    return client.post('/api/evidencia/subir',data={'key':'WO-SUST-1','tipo':'inicio','indice':'0','proyecto_id':str(caso['flm']),'cotizacion_key':'COT-SUST-TEST','foto':(foto(),'foto.png')})


def test_fuente_compartida_sin_mezclar_wos(app,auth_client,caso):
    auth_client.get('/switch_project/%s'%caso['cot'])
    r=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST');assert r.status_code==200
    assert [w['wo_data']['_BITACORA_INICIO'] for w in r.json['wos']]==['Comentario WO 1','Comentario WO 2']
    carga=cargar(auth_client,caso);assert carga.status_code==200,carga.json
    assert auth_client.get(carga.json['url']).status_code==200
    r=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','evidencia':{'_BITACORA_INICIO':'Editado en Cotizaciones','INICIO EJECUCION':'2026-10-12 09:00:00','FIN EJECUCION':'2026-10-12 17:00:00'}})
    assert r.status_code==200,r.json
    with app.app_context():
        d=json.loads(db.session.get(NucleusData,caso['ids'][0]).data_json)
        assert d['_BITACORA_INICIO']=='Editado en Cotizaciones'
        assert json.loads(d['_EVIDENCIA_INICIO'])[0]==carga.json['url']
        assert json.loads(db.session.get(NucleusData,caso['ids'][1]).data_json)['_BITACORA_INICIO']=='Comentario WO 2'
    auth_client.get('/switch_project/%s'%caso['flm'])
    assert auth_client.post('/api/rows/bulk_update',json={'key':'WO-SUST-1','data':{'_BITACORA_INICIO':'Editado en FLM'}}).status_code==200
    resultado=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST')
    assert resultado.json['wos'][0]['wo_data']['_BITACORA_INICIO']=='Editado en FLM'
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'OTRO','evidencia':{}}).status_code==400


def test_aprobacion_bloquea_todas_las_entradas_y_no_detalle(app,auth_client,caso):
    auth_client.get('/switch_project/%s'%caso['cot'])
    assert cargar(auth_client,caso).status_code==200
    assert auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1'}).status_code==200
    r=auth_client.post('/api/cotizacion/accion',json={'key':'COT-SUST-TEST','accion':'aprobar_sustento'});assert r.status_code==200,r.json
    assert r.json['newData']['_SUSTENTO_APROBADO']=='1'
    # Read-only downloads remain available after approval; editing stays locked.
    zip_url = f"/api/evidencia/zip/{caso['flm']}/WO-SUST-1?solo_fotos=1"
    assert auth_client.get(zip_url).status_code == 403
    assert auth_client.get(zip_url + '&cotizacion_key=COT-SUST-TEST').status_code == 200
    assert cargar(auth_client,caso).status_code==403
    assert auth_client.post('/api/evidencia/eliminar',json={'key':'WO-SUST-1','proyecto_id':caso['flm'],'tipo':'inicio','indice':0}).status_code==403
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','evidencia':{'_BITACORA_INICIO':'No'}}).status_code==403
    assert auth_client.post('/api/cotizacion/accion',json={'key':'COT-SUST-TEST','accion':'rechazar_sustento'}).status_code==403
    auth_client.get('/switch_project/%s'%caso['flm'])
    for key in ('WO-SUST-1','WO-SUST-2'):
        assert auth_client.post('/api/rows/update',json={'key':key,'field':'_BITACORA_INICIO','value':'No'}).status_code==403
        assert auth_client.post('/api/rows/bulk_update',json={'key':key,'data':{'_SUSTENTO_APROBADO_COT':''}}).status_code==403
    assert auth_client.post('/api/rows/bulk_update',json={'key':'WO-SUST-1','data':{'TECNICO ASIGNADO':'Técnico permitido'}}).status_code==200


def test_rechazo_conserva_y_devuelve_para_corregir(auth_client,caso):
    auth_client.get('/switch_project/%s'%caso['cot'])
    assert cargar(auth_client,caso).status_code==200
    assert auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1'}).status_code==200
    r=auth_client.post('/api/cotizacion/accion',json={'key':'COT-SUST-TEST','accion':'rechazar_sustento','motivo':'Completar fotos'})
    assert r.status_code==200 and r.json['pestania']=='sustentar'
    assert auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos'][0]['fotos_urls']['inicio']
    assert auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':'WO-SUST-1','evidencia':{'_BITACORA_CIERRE':'Corregido'}}).status_code==200


def test_adicionales_sin_flm_guardan_por_codigo_y_se_aprueban(app,auth_client,caso):
    with app.app_context():
        cot=db.session.get(NucleusData,caso['ids'][2]);d=json.loads(cot.data_json)
        d['NUMERO WO']='ADICIONAL-1, ADICIONAL-2';cot.data_json=json.dumps(d);db.session.commit()
    auth_client.get('/switch_project/%s'%caso['cot'])
    wos=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos']
    assert all(w['encontrado'] for w in wos)
    assert wos[0]['wo_data']['_key']!=wos[1]['wo_data']['_key']
    key=wos[0]['wo_data']['_key']
    carga=auth_client.post('/api/evidencia/subir',data={'key':key,'tipo':'inicio','indice':'0','proyecto_id':str(caso['cot']),'cotizacion_key':'COT-SUST-TEST','foto':(foto(),'foto.png')})
    assert carga.status_code==200,carga.json
    assert auth_client.get(carga.json['url']).status_code==200
    assert auth_client.get(f"/api/evidencia/zip/{caso['cot']}/{key}?solo_fotos=1&cotizacion_key=COT-SUST-TEST").status_code == 200
    for codigo,comentario in [('ADICIONAL-1','Primero'),('ADICIONAL-2','Segundo')]:
        r=auth_client.post('/api/cotizacion/sustento/wo',json={'key':'COT-SUST-TEST','wo':codigo,'evidencia':{'_BITACORA_INICIO':comentario}})
        assert r.status_code==200,r.json
    wos=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos']
    assert [w['wo_data']['_BITACORA_INICIO'] for w in wos]==['Primero','Segundo']
    assert wos[0]['fotos_urls']['inicio']==[carga.json['url']]
    assert not wos[1]['fotos_urls']['inicio']
    assert auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'COT-SUST-TEST','wo':'ADICIONAL-2'}).status_code==200
    assert auth_client.post('/api/cotizacion/accion',json={'key':'COT-SUST-TEST','accion':'rechazar_sustento'}).status_code==200
    assert auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos'][0]['fotos_urls']['inicio']==[carga.json['url']]
    assert auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'COT-SUST-TEST','wo':'ADICIONAL-1'}).status_code==200
    r=auth_client.post('/api/cotizacion/accion',json={'key':'COT-SUST-TEST','accion':'aprobar_sustento'});assert r.status_code==200,r.json
    wos=auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST').json['wos']
    assert all(w['bloqueado'] for w in wos)
    assert auth_client.post('/api/evidencia/eliminar',json={'key':key,'proyecto_id':caso['cot'],'tipo':'inicio','indice':0}).status_code==403
    liquidaciones=auth_client.get('/refacturable/api/registros')
    assert liquidaciones.status_code==200
    registros=liquidaciones.json
    if isinstance(registros,dict):registros=registros.get('registros',[])
    liquidacion=next(r for r in registros if r['cotizacion']=='COT-SUST-TEST')
    assert liquidacion['fotos']['inicio']==[carga.json['url']]
    assert 'Primero' in liquidacion['comentarios']['inicio'] and 'Segundo' in liquidacion['comentarios']['inicio']
    with app.app_context():
        assert NucleusData.query.filter_by(proyecto_id=caso['flm'],key_value='ADICIONAL-1').first() is None
