import io
import json
from services.rendicion_personal import completar_personal, documento, indice_personal
from db import db
from models import Proyecto, NucleusData, AppConfig


def test_cruce_solo_documento_y_respaldo_original():
    indice = {'00123456':[('Nombre Oficial','JUNIN')]}
    original = {'Nombre del proyecto':'Entel','Documento del beneficiario':'00 123 456','Técnico beneficiario':'nombre escrito como quiera'}
    row=completar_personal(original.copy(),indice)
    assert row['Técnico beneficiario']=='Nombre Oficial' and row['DEPARTAMENTO']=='JUNIN'
    assert row['VERIFICACIÓN PERSONAL']=='Verificado'
    assert row['_PERSONAL_ORIGINAL']['tecnico']==original['Técnico beneficiario']
    assert row['Documento del beneficiario']=='00 123 456'
    assert documento('00-123-456')=='00123456'


def test_desconocido_y_ambiguo_no_adivina():
    base={'Nombre del proyecto':'Entel','Documento del beneficiario':'12345678','Técnico beneficiario':'Nombre Form'}
    for indice in [{}, {'12345678':[('Persona Uno','LIMA'),('Persona Dos','ICA')]}]:
        row=completar_personal(base.copy(),indice)
        assert row['VERIFICACIÓN PERSONAL']=='Pendiente de verificar'
        assert row['Técnico beneficiario']=='Nombre Form' and 'DEPARTAMENTO' not in row
    row=completar_personal(base.copy(),{'12345678':[('Nombre Oficial','')]})
    assert row['VERIFICACIÓN PERSONAL']=='Pendiente de verificar'
    assert row['_PERSONAL_CRUCE']['estado']=='SIN DEPARTAMENTO EN PERSONAL'


def test_sync_cruza_solo_nuevas_y_no_reescribe_anteriores(app,auth_client,monkeypatch):
    with app.app_context():
        rend=Proyecto.query.filter_by(nombre='Rendicion').one()
        personal=Proyecto.query.filter_by(nombre='Dataper').first()
        if not personal:
            personal=Proyecto(nombre='Dataper');db.session.add(personal);db.session.flush()
        pid=personal.id; rid=rend.id
        cfg=AppConfig.query.filter_by(proyecto_id=rid,clave='rendicion_csv_url').first()
        previo=cfg.valor if cfg else None
        if not cfg: cfg=AppConfig(proyecto_id=rid,clave='rendicion_csv_url');db.session.add(cfg)
        cfg.valor='https://example.test/personal.csv'
        db.session.add(NucleusData(proyecto_id=pid,key_value='PERSONAL-CRUCE-TEST',data_json=json.dumps({'PROYECTO':'FLM','DOCUMENTO':'00123456','TECNICO':'Tecnico Oficial','DEPARTAMENTO':'JUNIN'})))
        db.session.add(NucleusData(proyecto_id=rid,key_value='CRUCE-ANTERIOR',data_json=json.dumps({'Técnico beneficiario':'Historico intacto'})))
        db.session.commit()
    csv='Marca temporal,Nombre del proyecto,Documento del beneficiario,Técnico beneficiario\nCRUCE-NUEVO,Entel,00123456,nombre informal\nCRUCE-ANTERIOR,Entel,00123456,nombre informal\nCRUCE-SIN-MATCH,Claro,00123456,otro\n'
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**k:io.BytesIO(csv.encode('utf-8')))
    try:
        response=auth_client.post('/api/rendicion/sync')
        assert response.status_code==200,response.json
        assert response.json['personal_verificado']==2
        assert response.json['personal_pendiente_verificar']==0
        with app.app_context():
            nuevo=json.loads(NucleusData.query.filter_by(proyecto_id=rid,key_value='CRUCE-NUEVO').one().data_json)
            assert nuevo['Técnico beneficiario']=='Tecnico Oficial' and nuevo['DEPARTAMENTO']=='JUNIN'
            assert nuevo['_PERSONAL_ORIGINAL']['tecnico']=='nombre informal'
            claro=json.loads(NucleusData.query.filter_by(proyecto_id=rid,key_value='CRUCE-SIN-MATCH').one().data_json)
            assert claro['Técnico beneficiario']=='Tecnico Oficial' and claro['DEPARTAMENTO']=='JUNIN'
            anterior=json.loads(NucleusData.query.filter_by(proyecto_id=rid,key_value='CRUCE-ANTERIOR').one().data_json)
            assert anterior=={'Técnico beneficiario':'Historico intacto'}
        response=auth_client.post('/api/rendicion/sync')
        assert response.json['nuevas']==0
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.proyecto_id==rid,NucleusData.key_value.like('CRUCE-%')).delete(synchronize_session=False)
            NucleusData.query.filter_by(proyecto_id=pid,key_value='PERSONAL-CRUCE-TEST').delete()
            cfg=AppConfig.query.filter_by(proyecto_id=rid,clave='rendicion_csv_url').one()
            if previo is None:db.session.delete(cfg)
            else:cfg.valor=previo
            db.session.commit()



def test_sin_proyecto_y_repetidos_identicos():
    row = completar_personal({'DNI':'00123456','Técnico beneficiario':'Original'}, {'00123456':[('Nombre Oficial','JUNIN'),('Nombre Oficial','JUNIN')]})
    assert row['VERIFICACIÓN PERSONAL']=='Verificado'
    assert row['Técnico beneficiario']=='Nombre Oficial'
    assert row['_PERSONAL_CRUCE']['criterio']=='DOCUMENTO'
