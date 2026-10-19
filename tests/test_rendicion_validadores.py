import json
import pytest
from db import db
from models import Usuario, Proyecto, NucleusData, AppConfig, AccesoProyecto
from flask import g
from services.rendicion_validadores import CLAVE


@pytest.fixture
def escenario(app, auth_client, monkeypatch):
    import blueprints.rendicion as flujo
    monkeypatch.setattr(flujo, '_avisar_flujo', lambda *a: None)
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre='Rendicion').one()
        usuario = Usuario(username='validador-proyecto-test',nombre='Validador de Prueba',password_hash='test',rol='supervisor')
        db.session.add(usuario);db.session.flush()
        uid,pid=usuario.id,proy.id
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one()
        db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=entel.id, restricciones='{}'))
        prev = AppConfig.query.filter_by(proyecto_id=pid,clave=CLAVE).first()
        valor=prev.valor if prev else None
        for operador in ('ENTEL','CLARO','INTEGRATEL','DESCONOCIDO'):
            db.session.add(NucleusData(proyecto_id=pid,key_value='VAL-'+operador,data_json=json.dumps({'Nombre del proyecto':'FLM - '+operador,'ESTADO':'PENDIENTE'})))
        db.session.commit()
    auth_client.get(f'/switch_project/{pid}')
    yield uid,pid
    with app.app_context():
        NucleusData.query.filter(NucleusData.proyecto_id==pid,NucleusData.key_value.like('VAL-%')).delete(synchronize_session=False)
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave=CLAVE).first()
        if cfg:
            if valor is None:db.session.delete(cfg)
            else:cfg.valor=valor
        AccesoProyecto.query.filter_by(usuario_id=uid).delete()
        db.session.delete(db.session.get(Usuario,uid));db.session.commit()
        g.pop('_rend_validadores',None);g.pop('_nombres_presentacion',None)


def test_validacion_asignada_y_rechazo_del_servidor(app,auth_client,escenario):
    uid,pid=escenario
    response=auth_client.post('/api/rendicion/validadores',json={'activo':True,'asignaciones':{str(uid):['ENTEL']}})
    assert response.status_code==200
    with auth_client.session_transaction() as s:
        s['user_id']=uid;s['username']='validador-proyecto-test';s['rol']='supervisor'
    for operador in ('CLARO','INTEGRATEL','DESCONOCIDO'):
        response=auth_client.post('/api/rendicion/accion',json={'key':'VAL-'+operador,'accion':'validar'})
        assert response.status_code==404,response.json
        with app.app_context():
            d=json.loads(NucleusData.query.filter_by(proyecto_id=pid,key_value='VAL-'+operador).one().data_json)
            assert d['ESTADO']=='PENDIENTE'
    # Con permiso de proyecto aún rigen las demás exigencias del flujo (ej. correo).
    response=auth_client.post('/api/rendicion/accion',json={'key':'VAL-ENTEL','accion':'validar'})
    assert response.status_code not in (403,404),response.json
    assert auth_client.post('/api/rendicion/validadores',json={'activo':False,'asignaciones':{}}).status_code==403
    assert auth_client.get('/api/rendicion/validadores').status_code==403


def test_configuracion_valida_y_compatibilidad(app,auth_client,escenario):
    from services.rendicion_validadores import puede_validar
    uid,pid=escenario
    assert auth_client.post('/api/rendicion/validadores',json={'activo':True,'asignaciones':{str(uid):['OTRO']}}).status_code==400
    assert auth_client.post('/api/rendicion/validadores',json={'activo':True,'asignaciones':{'99999999':['ENTEL']}}).status_code==400
    assert auth_client.post('/api/rendicion/validadores',json={'activo':True,'asignaciones':{str(uid):['ENTEL','CLARO']}}).status_code==200
    with app.test_request_context():
        assert puede_validar({'Nombre del proyecto':'Claro'},uid,'supervisor')
        assert not puede_validar({'Nombre del proyecto':'INTEGRATEL'},uid,'supervisor')
        assert not puede_validar({'Nombre del proyecto':'ENTEL'},-999,'supervisor')
        assert puede_validar({'Nombre del proyecto':'INTEGRATEL'},uid,'zeno')
    assert auth_client.post('/api/rendicion/validadores',json={'activo':False,'asignaciones':{}}).status_code==200
    with app.test_request_context():
        assert puede_validar({'Nombre del proyecto':'INTEGRATEL'},uid,'supervisor')


def test_nombre_visual_preserva_auditoria(app,auth_client,escenario):
    uid,pid=escenario
    with app.app_context():
        row=NucleusData.query.filter_by(proyecto_id=pid,key_value='VAL-ENTEL').one()
        datos=json.loads(row.data_json);datos['VALIDADO POR']='validador-proyecto-test';row.data_json=json.dumps(datos);db.session.commit()
    response=auth_client.get('/')
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert 'Validador de Prueba' in html and 'validador-proyecto-test' in html
    assert 'Validadores por proyecto' in html
    with app.app_context():
        assert json.loads(NucleusData.query.filter_by(proyecto_id=pid,key_value='VAL-ENTEL').one().data_json)['VALIDADO POR']=='validador-proyecto-test'


def test_no_se_puede_validar_con_edicion_generica(auth_client,escenario):
    uid,pid=escenario
    auth_client.post('/api/rendicion/validadores',json={'activo':True,'asignaciones':{str(uid):['ENTEL']}})
    with auth_client.session_transaction() as s:
        s['user_id']=uid;s['username']='validador-proyecto-test';s['rol']='supervisor'
    assert auth_client.post('/api/rows/update',json={'key':'VAL-CLARO','field':'ESTADO','value':'VALIDADO'}).status_code==404
    assert auth_client.post('/api/rows/bulk_update',json={'key':'VAL-CLARO','data':{'ESTADO':'VALIDADO'}}).status_code==404
    assert auth_client.post('/api/rows/update',json={'key':'VAL-CLARO','field':'Nombre del proyecto','value':'ENTEL'}).status_code==404



def test_lista_incluye_usuarios_sin_modulo(auth_client, escenario):
    uid, _ = escenario
    respuesta = auth_client.get('/api/rendicion/validadores')
    assert respuesta.status_code == 200
    usuario = next(u for u in respuesta.json['usuarios'] if u['id'] == uid)
    assert usuario['nombre'] == 'Validador de Prueba'
    assert usuario['acceso_rendicion'] is False
    assert usuario['admin'] is False
    assert auth_client.post('/api/rendicion/validadores', json={'activo': True, 'asignaciones': {str(uid): ['ENTEL']}}).status_code == 200


def test_acceso_rendicion_equivale_a_la_regla_individual(app, auth_client, escenario):
    """La lista resuelve el acceso de todos los usuarios en bloque (dos consultas
    fijas en vez de una por usuario): debe coincidir usuario por usuario con la
    regla individual `puede_rendicion`."""
    from models import Usuario
    from services.utilidades import puede_rendicion
    respuesta = auth_client.get('/api/rendicion/validadores')
    assert respuesta.status_code == 200
    usuarios = respuesta.json['usuarios']
    with app.test_request_context():
        esperado = {u.id: bool(puede_rendicion(u.id, u.rol, '')) for u in Usuario.query.all()}
    assert {u['id'] for u in usuarios} == set(esperado)
    for usuario in usuarios:
        assert usuario['acceso_rendicion'] is esperado[usuario['id']], usuario['username']
    # La base de prueba cubre las dos ramas: zeno siempre entra, el supervisor no.
    assert any(usuario['acceso_rendicion'] for usuario in usuarios)
    assert any(not usuario['acceso_rendicion'] for usuario in usuarios)
