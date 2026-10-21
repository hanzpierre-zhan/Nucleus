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
    # Una configuración antigua sin asignaciones ya no bloquea los proyectos permitidos.
    with app.app_context():
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=CLAVE).first()
        if not cfg:
            cfg = AppConfig(proyecto_id=pid, clave=CLAVE)
            db.session.add(cfg)
        cfg.valor = json.dumps({'activo': True, 'asignaciones': {}})
        db.session.commit()
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
    assert auth_client.post('/api/rendicion/validadores',json={'activo':False,'asignaciones':{}}).status_code==410
    assert auth_client.get('/api/rendicion/validadores').status_code==410


def test_configuracion_retirada(auth_client, escenario):
    assert auth_client.get('/api/rendicion/validadores').status_code == 410
    assert auth_client.post('/api/rendicion/validadores', json={'activo': True, 'asignaciones': {}}).status_code == 410


def test_nombre_visual_preserva_auditoria(app,auth_client,escenario):
    uid,pid=escenario
    with app.app_context():
        row=NucleusData.query.filter_by(proyecto_id=pid,key_value='VAL-ENTEL').one()
        datos=json.loads(row.data_json);datos['VALIDADO POR']='validador-proyecto-test';row.data_json=json.dumps(datos);db.session.commit()
    response=auth_client.get('/')
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert 'Validador de Prueba' in html and 'validador-proyecto-test' in html
    assert 'Validadores por proyecto' not in html
    assert 'rend-validator-dialog' not in html
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
