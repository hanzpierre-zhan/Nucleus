import json
import pytest
from db import db
from models import Proyecto, AppConfig, NucleusData, AccesoProyecto


@pytest.mark.parametrize('rol', ['supervisor','suport','zeno'])
def test_roles_pueden_cambiar_opciones_sin_cambiar_datos(app, auth_client, rol):
    with auth_client.session_transaction() as session: uid=session['user_id']
    with app.app_context():
        project=Proyecto(nombre='Opciones '+rol);db.session.add(project);db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=project.id, restricciones='{}'))
        db.session.add(AppConfig(proyecto_id=project.id,clave='manual_columns',valor=json.dumps([{'nombre':'CAMPO','tipo':'lista','opciones':['Antigua','Otra']}])) )
        row=NucleusData(proyecto_id=project.id,key_value='O-'+rol,data_json=json.dumps({'CAMPO':'Antigua'}));db.session.add(row);db.session.commit();pid=project.id;rid=row.id
    with auth_client.session_transaction() as session:
        session['rol']=rol;session['current_proyecto_id']=pid;session['current_proyecto_nombre']=project.nombre
    response=auth_client.patch('/api/master/manual_columns/options',json={'nombre':'CAMPO','opciones':['Nueva','Otra','Nueva']})
    assert response.status_code == 200 and response.json['opciones']==['Nueva','Otra']
    assert json.loads(db.session.get(NucleusData,rid).data_json)['CAMPO']=='Antigua'


def test_otro_rol_no_puede_administrar_opciones(auth_client,cambiar_rol):
    cambiar_rol(auth_client, 'gestor')
    assert auth_client.patch('/api/master/manual_columns/options',json={'nombre':'CAMPO','opciones':['Nueva']}).status_code==403


def test_lista_del_formulario_persiste_sin_modificar_valor_historico(app,auth_client):
    with app.app_context():
        project=Proyecto.query.filter_by(nombre='FLM - ENTEL').one()
        pid=project.id
        config=AppConfig.query.filter_by(proyecto_id=pid,clave='manual_columns').first()
        previous=config.valor if config else None
        row=NucleusData(proyecto_id=pid,key_value='FORM-OPTIONS-TEST',data_json=json.dumps({'REQUIERE CORRECTIVO FINAL':'Sí'}))
        db.session.add(row);db.session.commit();rid=row.id
    auth_client.get(f'/switch_project/{pid}')
    try:
        first=auth_client.get('/api/master/manual_columns/options')
        assert first.status_code==200
        assert any(c['nombre']=='REQUIERE CORRECTIVO FINAL' for c in first.json['campos'])
        response=auth_client.patch('/api/master/manual_columns/options',json={'nombre':'REQUIERE CORRECTIVO FINAL','opciones':['No','Por confirmar']})
        assert response.status_code==200
        saved=auth_client.get('/api/master/manual_columns/options').json['campos']
        field=next(c for c in saved if c['nombre']=='REQUIERE CORRECTIVO FINAL')
        assert field['configurada'] and field['opciones']==['No','Por confirmar']
        with app.app_context():
            assert json.loads(db.session.get(NucleusData,rid).data_json)['REQUIERE CORRECTIVO FINAL']=='Sí'
        assert auth_client.patch('/api/master/manual_columns/options',json={'nombre':'CLIENTE','opciones':['Nuevo operador']}).status_code==400
        assert auth_client.patch('/api/master/manual_columns/options',json={'nombre':'CAMPO INEXISTENTE','opciones':['Nueva']}).status_code==404
    finally:
        with app.app_context():
            db.session.delete(db.session.get(NucleusData,rid))
            config=AppConfig.query.filter_by(proyecto_id=pid,clave='manual_columns').one()
            if previous is None:db.session.delete(config)
            else:config.valor=previous
            db.session.commit()
