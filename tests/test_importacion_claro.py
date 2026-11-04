import io
import json
import pytest
from db import db
from models import Proyecto, AppConfig, NucleusData, NucleusHistory


def test_migracion_clave_no_modifica_registros_y_es_idempotente(app):
    from migrations.claro_identificador import instalar, VERSION
    with app.app_context():
        p=Proyecto.query.filter_by(nombre='FLM - CLARO').one()
        previos=[(r.id,r.key_value,r.data_json) for r in NucleusData.query.filter_by(proyecto_id=p.id)]
        cfg=AppConfig.query.filter_by(proyecto_id=p.id,clave='primary_key').one()
        cfg.valor='Número de WO'
        AppConfig.query.filter_by(proyecto_id=p.id,clave=VERSION).delete()
        AppConfig.query.filter_by(proyecto_id=p.id,clave=VERSION+'_backup').delete()
        db.session.commit();instalar();instalar()
        assert cfg.valor=='Ticket Id'
        assert [(r.id,r.key_value,r.data_json) for r in NucleusData.query.filter_by(proyecto_id=p.id)]==previos
        backup=AppConfig.query.filter_by(proyecto_id=p.id,clave=VERSION+'_backup').one()
        assert json.loads(backup.valor)['primary_key']=='Número de WO'


@pytest.fixture
def claro(app, auth_client):
    with app.app_context():
        p=Proyecto.query.filter_by(nombre='FLM - CLARO').one();pid=p.id
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='primary_key').one()
        previo=cfg.valor;cfg.valor='Número de WO';db.session.commit()
    auth_client.get('/switch_project/%s'%pid)
    yield pid
    with app.app_context():
        NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.key_value.like('QA-%')).delete(synchronize_session=False)
        NucleusHistory.query.filter_by(proyecto_id=pid).filter(NucleusHistory.key_value.like('QA-%')).delete(synchronize_session=False)
        AppConfig.query.filter_by(proyecto_id=pid,clave='primary_key').one().valor=previo
        db.session.commit()


def importar(c, texto, **extra):
    return c.post('/api/import/process',data={'type':'base','file':(io.BytesIO(texto.encode()),'claro.csv'),**extra})


def test_tipo_repetido_no_colapsa_y_reimportar_respalda(app,auth_client,claro):
    csv='Task Type,Ticket Id,Title\nCM,QA-1,Primero\nCM,QA-2,Segundo\nPM,QA-3,Tercero\n'
    r=importar(auth_client,csv)
    assert r.status_code==200,r.json
    assert r.json['added']==3 and r.json['pk']=='Ticket Id'
    r=importar(auth_client,csv.replace('Primero','Cambio'))
    assert r.status_code==200,r.json
    with app.app_context():
        rows=NucleusData.query.filter_by(proyecto_id=claro).filter(NucleusData.key_value.like('QA-%')).all()
        assert {r.key_value for r in rows}=={'QA-1','QA-2','QA-3'}
        h=NucleusHistory.query.filter_by(proyecto_id=claro,key_value='QA-1').one()
        assert json.loads(h.data_json)['Title']=='Primero'


@pytest.mark.parametrize('csv,extra',[
    ('Task Type,Title\nCM,Sin clave\n',{}),
    ('Task Type,Ticket Id\nCM,QA-1\nPM,QA-1\n',{}),
    ('Task Type,Ticket Id\nCM,\n',{}),
    ('Task Type,Ticket Id\nCM,QA-1\n',{'file_key':'Task Type'}),
])
def test_archivo_invalido_no_modifica_nada(app,auth_client,claro,csv,extra):
    with app.app_context():
        previo=[(r.id,r.key_value,r.data_json) for r in NucleusData.query.filter_by(proyecto_id=claro).all()]
    r=importar(auth_client,csv,**extra)
    assert r.status_code==400,r.json
    with app.app_context():
        assert [(r.id,r.key_value,r.data_json) for r in NucleusData.query.filter_by(proyecto_id=claro).all()]==previo
