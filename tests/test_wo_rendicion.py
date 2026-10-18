import json
import pytest
from db import db
from models import Proyecto,NucleusData


def test_clave_wo_compartida_no_mezcla_rendiciones(app,auth_client):
    with app.app_context():
        ids={p.nombre:p.id for p in Proyecto.query.all()};filas=[]
        for n in ('FLM - CLARO','FLM - INTEGRATEL'):
            filas.append(NucleusData(proyecto_id=ids[n],key_value='WO-COMPARTIDA',data_json='{}'))
        for i,n in enumerate(('Claro','Integratel','')):
            filas.append(NucleusData(proyecto_id=ids['Rendicion'],key_value='REND-COMPARTIDA-'+str(i),data_json=json.dumps({'Número CM / PM / PLM':'WO-COMPARTIDA','Nombre del proyecto':n,'Técnico beneficiario':n or 'Sin proyecto'})))
        db.session.add_all(filas);db.session.commit();creados=[x.id for x in filas]
    try:
        r=auth_client.get('/api/rendicion/por_wo',query_string={'key':'WO-COMPARTIDA','proyecto_id':ids['FLM - CLARO']})
        assert r.status_code==200
        assert [x['tecnico'] for x in r.json['lista']]==['Claro']
        from blueprints.cotizacion import _resolver_wo_sustento
        with app.app_context():
            assert _resolver_wo_sustento('WO-COMPARTIDA') is None
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(creados)).delete(synchronize_session=False);db.session.commit()

@pytest.mark.parametrize('nombre',['FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO'])
def test_pestanas_y_rendiciones_por_wo(app,auth_client,nombre):
    with app.app_context():
        p=Proyecto.query.filter_by(nombre=nombre).one();r=Proyecto.query.filter_by(nombre='Rendicion').one();pid=p.id
        wo=NucleusData(proyecto_id=p.id,key_value='CM-REND-TEST',data_json='{}')
        rend=NucleusData(proyecto_id=r.id,key_value='SOL-REND-TEST',data_json=json.dumps({'Número CM / PM / PLM':'CM-REND-TEST','ESTADO':'VALIDADO','Técnico beneficiario':'Prueba','Monto total del depósito':'100','Motivo de la solicitud':'Obra'}))
        otra=NucleusData(proyecto_id=r.id,key_value='SOL-OTRA-TEST',data_json=json.dumps({'Número CM / PM / PLM':'CM-REND-TEST-OTRO'}))
        db.session.add_all([wo,rend,otra]);db.session.commit();ids=[wo.id,rend.id,otra.id]
    try:
        auth_client.get('/switch_project/%s'%pid)
        html=auth_client.get('/').text
        assert 'id="wo-tab-rendicion"' in html
        assert 'id="wo-tab-resguardo"' not in html
        assert 'id="wo-tab-estado"' not in html
        res=auth_client.get('/api/rendicion/por_wo',query_string={'key':'cm-rend-test','proyecto_id':pid})
        # La existencia del WO conserva su clave exacta; la vinculación ignora mayúsculas.
        assert res.status_code==404
        res=auth_client.get('/api/rendicion/por_wo',query_string={'key':'CM-REND-TEST','proyecto_id':pid})
        assert res.status_code==200,res.json
        assert len(res.json['lista'])==1
        assert res.json['lista'][0]['estado']=='VALIDADO'
        assert res.json['lista'][0]['tecnico']=='Prueba'
        assert auth_client.get('/api/rendicion/por_wo',query_string={'key':'CM-REND-TEST','proyecto_id':999999}).status_code==403
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()


@pytest.mark.parametrize('nombre',['FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO'])
def test_fechas_ejecucion_persisten_y_validan(app,auth_client,nombre):
    with app.app_context():
        p=Proyecto.query.filter_by(nombre=nombre).one();pid=p.id
        fila=NucleusData(proyecto_id=pid,key_value='WO-EJECUCION-TEST',data_json='{}');db.session.add(fila);db.session.commit();id=fila.id
    try:
        auth_client.get('/switch_project/%s'%pid)
        r=auth_client.post('/api/rows/bulk_update',json={'key':'WO-EJECUCION-TEST','data':{'INICIO EJECUCION':'2026-10-12 09:00:00','FIN EJECUCION':'2026-10-12 17:00:00'}})
        assert r.status_code==200,r.json
        with app.app_context():
            datos=json.loads(db.session.get(NucleusData,id).data_json)
            assert datos['INICIO EJECUCION']=='2026-10-12 09:00:00'
            assert datos['FIN EJECUCION']=='2026-10-12 17:00:00'
        assert auth_client.post('/api/rows/update',json={'key':'WO-EJECUCION-TEST','field':'FIN EJECUCION','value':'2026-10-11 17:00:00'}).status_code==400
        assert auth_client.post('/api/rows/bulk_update',json={'key':'WO-EJECUCION-TEST','data':{'INICIO EJECUCION':'no es fecha'}}).status_code==400
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=id).delete();db.session.commit()
