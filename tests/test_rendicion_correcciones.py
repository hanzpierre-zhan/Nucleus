import json
import pytest
from db import db
from models import Proyecto, NucleusData, HistorialCambios
from services.rendicion_personal import completar_personal


@pytest.fixture
def solicitud(app,auth_client):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        row=NucleusData(proyecto_id=pid,key_value='CORRECCION-PRUEBA',data_json=json.dumps({'ESTADO':'PENDIENTE','Nombre del proyecto':'Entel','Técnico beneficiario':'Nombre inicial','DEPARTAMENTO':'LIMA','Documento del beneficiario':'00123456','Motivo de la solicitud':'Inicial','Monto total del depósito':'100.00','FOTO PAGO':'/pago.jpg'}))
        db.session.add(row);db.session.commit();rid=row.id
    auth_client.get(f'/switch_project/{pid}')
    with auth_client.session_transaction() as s:s['rol']='gestor'
    yield rid,pid
    with app.app_context():
        HistorialCambios.query.filter_by(proyecto_id=pid,key_value='CORRECCION-PRUEBA').delete()
        db.session.delete(db.session.get(NucleusData,rid));db.session.commit()


def guardar(client,cambios,revision=0):
    return client.patch('/api/rendicion/solicitud',json={'key':'CORRECCION-PRUEBA','cambios':cambios,'revision':revision})


def test_gestor_corrige_con_historial_sin_validar(app,auth_client,solicitud):
    rid,pid=solicitud
    response=guardar(auth_client,{'Técnico beneficiario':'Nombre corregido','DEPARTAMENTO':'JUNIN','Motivo de la solicitud':'Corregido','Monto total del depósito':'125.50'})
    assert response.status_code==200,response.json
    row=response.json['newData']
    assert row['ESTADO']=='PENDIENTE' and row['FOTO PAGO']=='/pago.jpg'
    assert row['Técnico beneficiario']=='Nombre corregido' and row['DEPARTAMENTO']=='JUNIN'
    assert row['_CORRECCION_REV']==1
    # El cruce no debe borrar la corrección deliberada del gestor.
    vista=completar_personal(dict(row),{'00123456':[('Nombre catalogo','LIMA')]})
    assert vista['Técnico beneficiario']=='Nombre corregido' and vista['DEPARTAMENTO']=='JUNIN'
    with app.app_context():
        historial=HistorialCambios.query.filter_by(proyecto_id=pid,key_value='CORRECCION-PRUEBA').all()
        cambio=next(c for c in historial if c.campo_modificado=='Técnico beneficiario')
        assert cambio.valor_anterior=='Nombre inicial' and cambio.valor_nuevo=='Nombre corregido'
        assert cambio.username
    assert guardar(auth_client,{'Motivo de la solicitud':'Viejo'},revision=0).status_code==409
    assert guardar(auth_client,{'Motivo de la solicitud':'Otro'},revision=1).status_code==200


def test_campos_y_etapas_protegidos(app,auth_client,solicitud):
    rid,pid=solicitud
    for cambios in [{'ESTADO':'VALIDADO'},{'Nombre del proyecto':'Claro'},{'FOTO PAGO':'/otro.jpg'},{'Marca temporal':'otra'},{'Monto total del depósito':'-5'},{'Documento del beneficiario':''}]:
        assert guardar(auth_client,cambios).status_code==400
    with app.app_context():
        row=db.session.get(NucleusData,rid);datos=json.loads(row.data_json);datos['ESTADO']='VALIDADO';row.data_json=json.dumps(datos);db.session.commit()
    assert guardar(auth_client,{'Motivo de la solicitud':'Cambio'}).status_code==409


def test_contrata_no_puede_corregir(auth_client,solicitud,cambiar_rol):
    cambiar_rol(auth_client, 'contrata')
    assert guardar(auth_client,{'Motivo de la solicitud':'Cambio'}).status_code==403


def test_correccion_respeta_asignacion(auth_client,solicitud,monkeypatch):
    monkeypatch.setattr('services.rendicion_validadores.puede_validar',lambda *a:False)
    assert guardar(auth_client,{'Motivo de la solicitud':'No permitido'}).status_code==403
