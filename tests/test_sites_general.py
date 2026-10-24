import json
from collections import Counter
from db import db
from models import Proyecto,NucleusData,TokenStore,AppConfig
from services import sites_general as maestro

def test_archivo_completo_y_clave_que_no_descarta_codigos_repetidos():
    rows=maestro.cargar()['rows']
    assert Counter(r['PROYECTO'] for r in rows)=={'ENTEL':5583,'CLARO':9022,'INTEGRATEL':3999}
    assert len({r['Site'] for r in rows})==18604
    assert len({r['Código'] for r in rows})<18604

def test_encabezados_y_orden_excel_en_la_tabla(app):
    with app.app_context():
        site=Proyecto.query.filter_by(nombre='SITE').one()
        config={r.clave:json.loads(r.valor) for r in AppConfig.query.filter_by(proyecto_id=site.id)
                if r.clave in ('manual_columns','column_layout')}
        assert [c['nombre'] for c in config['manual_columns']]==maestro.EXCEL_KEYS
        assert [c['field'] for c in config['column_layout']]==['_key']+maestro.EXCEL_KEYS[1:]
        row=NucleusData.query.filter_by(proyecto_id=site.id).first()
        datos=json.loads(row.data_json)
        assert list(datos)==maestro.EXCEL_KEYS
        assert datos['Proyecto'].startswith('FLM - ')

def test_reemplazo_respaldo_completar_sin_pisar_y_una_sola_vez(app,monkeypatch):
    with app.app_context():
        transaction=db.session.begin_nested()
        monkeypatch.setattr(db.session,'commit',db.session.flush)
        monkeypatch.setattr(maestro,'VERSION','sites_test_version')
        monkeypatch.setattr(maestro,'BACKUP','sites_test_backup')
        site=Proyecto.query.filter_by(nombre='SITE').one()
        cot=Proyecto.query.filter_by(nombre='Cotizaciones').one()
        rows=maestro.cargar()['rows'][:2]
        monkeypatch.setattr(maestro,'cargar',lambda:{'source':'test.xlsx','sha256':'test','rows':rows})
        old=NucleusData(proyecto_id=site.id,key_value='VIEJO-TEST',data_json='{}')
        ficha={'site_name':'0'+rows[0]['Site'],'site_address':'Dirección escrita por el gestor','item_photos':{'x':[{'url':'foto'}]}}
        datos={'CLIENTE':'ENTEL','_SUSTENTO_FICHAS':{'wo':ficha},'NUMERO WO':'WO'}
        registro=NucleusData(proyecto_id=cot.id,key_value='COT-SITE-MIG',data_json=json.dumps(datos))
        db.session.add_all([old,registro]);db.session.flush()
        try:
            maestro.aplicar()
            assert NucleusData.query.filter_by(proyecto_id=site.id).count()==2
            assert db.session.get(NucleusData,registro.id) is registro
            updated=json.loads(registro.data_json)['_SUSTENTO_FICHAS']['wo']
            assert updated['site_id']==rows[0]['Código']
            assert updated['site_address']=='Dirección escrita por el gestor'
            assert updated['item_photos']==ficha['item_photos']
            backup=json.loads(TokenStore.query.filter_by(clave=maestro.BACKUP).one().valor)
            assert any(r['key']=='VIEJO-TEST' for r in backup['rows'])
            assert backup['cotizaciones'][0]['data_json']==json.dumps(datos)
            assert AppConfig.query.filter_by(proyecto_id=site.id,clave='primary_key').one().valor=='Site'
            record=NucleusData.query.filter_by(proyecto_id=site.id).first()
            record.data_json='{"edicion":"se conserva"}';db.session.flush()
            maestro.aplicar()
            assert record.data_json=='{"edicion":"se conserva"}'
        finally:
            transaction.rollback()
            db.session.rollback()

def test_busqueda_por_proyecto_y_cualquier_campo(app,auth_client):
    for field,value in [('site_id','130002'),('site_type','Caseta'),('district','COMAS'),('province','LIMA'),('region','CENTRO')]:
        response=auth_client.get('/api/cotizacion/sustento/sites',query_string={'q':value,'field':field,'proyecto':'ENTEL'})
        assert response.status_code==200
        assert response.json['sites']
        assert all(value.casefold() in r[field].casefold() for r in response.json['sites'])
    response=auth_client.get('/api/cotizacion/sustento/sites',query_string={'q':'130002','field':'site_id','proyecto':'CLARO'})
    assert not any(r['site_key']=='130002_LM_Nuevo_Comas' for r in response.json['sites'])
