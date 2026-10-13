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


def test_otro_rol_no_puede_administrar_opciones(auth_client):
    with auth_client.session_transaction() as session: session['rol']='gestor'
    assert auth_client.patch('/api/master/manual_columns/options',json={'nombre':'CAMPO','opciones':['Nueva']}).status_code==403
