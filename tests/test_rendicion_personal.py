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


def test_sync_completa_anteriores_sin_alterar_flujo_y_respaldo(app,auth_client,monkeypatch):
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
        db.session.add(NucleusData(proyecto_id=rid,key_value='CRUCE-ANTERIOR',data_json=json.dumps({'Técnico beneficiario':'Nombre anterior','Documento del beneficiario':'00123456','ESTADO':'DEPOSITADO','MONTO PAGO':'88.50','FOTO PAGO':'/evidencia/pago.jpg'})))
        db.session.commit()
    csv='Marca temporal,Nombre del proyecto,Documento del beneficiario,Técnico beneficiario\nCRUCE-NUEVO,Entel,00123456,nombre informal\nCRUCE-ANTERIOR,Entel,00123456,nombre informal\nCRUCE-SIN-MATCH,Claro,00123456,otro\n'
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**k:io.BytesIO(csv.encode('utf-8')))
    try:
        auth_client.get(f'/switch_project/{rid}')
        vista = auth_client.get('/')
        assert vista.status_code == 200
        assert 'DEPARTAMENTO' in vista.get_data(as_text=True)
        assert 'Tecnico Oficial' in vista.get_data(as_text=True)
        with app.app_context():
            antes = json.loads(NucleusData.query.filter_by(proyecto_id=rid,key_value='CRUCE-ANTERIOR').one().data_json)
            assert antes['Técnico beneficiario'] == 'Nombre anterior'
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
            assert anterior['Técnico beneficiario']=='Tecnico Oficial' and anterior['DEPARTAMENTO']=='JUNIN'
            assert anterior['_PERSONAL_ORIGINAL']['tecnico']=='Nombre anterior'
            assert anterior['ESTADO']=='DEPOSITADO' and anterior['MONTO PAGO']=='88.50'
            assert anterior['FOTO PAGO']=='/evidencia/pago.jpg'
        response=auth_client.post('/api/rendicion/sync')
        assert response.json['nuevas']==0
        assert response.json['personal_actualizado']==0
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


def test_expone_columnas_de_auditoria_del_cruce():
    # El nombre ingresado se aísla en 'Técnico beneficiario (Form)' y el oficial
    # (cruce por documento con Dataper) en 'Técnico beneficiario'.
    indice = {'00123456':[('Nombre Oficial','JUNIN')]}
    row = completar_personal({'Documento del beneficiario':'00 123 456','Técnico beneficiario':'nombre escrito como quiera'}, indice)
    assert row['Técnico beneficiario (Form)'] == 'nombre escrito como quiera'
    assert row['Documento del beneficiario (Form)'] == '00 123 456'
    assert row['Técnico beneficiario'] == 'Nombre Oficial'
    assert row['Cruce de personal'] == 'VERIFICADO'

    # Documento no encontrado: se conserva lo ingresado y el estado lo refleja.
    sin_match = completar_personal({'Documento del beneficiario':'99999999','Técnico beneficiario':'Desconocido'}, {})
    assert sin_match['Cruce de personal'] == 'NO ENCONTRADO'
    assert sin_match['Técnico beneficiario (Form)'] == 'Desconocido'
    assert sin_match['Técnico beneficiario'] == 'Desconocido'

    # Sin documento.
    sin_doc = completar_personal({'Técnico beneficiario':'Alguien'}, {})
    assert sin_doc['Cruce de personal'] == 'SIN DOCUMENTO'
    assert sin_doc['Técnico beneficiario (Form)'] == 'Alguien'

    # Corrección manual del gestor.
    manual = completar_personal({'Documento del beneficiario':'00123456','Técnico beneficiario':'x','_PERSONAL_CORRECCION_MANUAL':True}, indice)
    assert manual['Cruce de personal'] == 'CORREGIDO MANUALMENTE'
    assert manual['Técnico beneficiario (Form)'] == 'x'
