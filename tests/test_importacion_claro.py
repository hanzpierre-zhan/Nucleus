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


def test_reimportacion_masiva_no_recarga_fila_por_fila(app, auth_client, claro):
    from sqlalchemy import event

    cantidad = 1200
    csv = 'Task Type,Ticket Id,Title\n' + ''.join(
        f'CM,QA-masivo-{indice},Original\n' for indice in range(cantidad)
    )
    primera = importar(auth_client, csv)
    assert primera.status_code == 200, primera.json
    assert primera.json['added'] == cantidad

    lecturas = []

    def contar_lecturas(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'FROM nucleus_data' in statement:
            lecturas.append(statement)

    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', contar_lecturas)
    try:
        segunda = importar(auth_client, csv.replace('Original', 'Actualizado'))
    finally:
        event.remove(engine, 'before_cursor_execute', contar_lecturas)

    assert segunda.status_code == 200, segunda.json
    assert segunda.json['updated'] == cantidad
    assert len(lecturas) <= 5
    with app.app_context():
        filas = NucleusData.query.filter_by(proyecto_id=claro).filter(
            NucleusData.key_value.like('QA-masivo-%')
        ).all()
        assert len(filas) == cantidad
        assert all(json.loads(fila.data_json)['Title'] == 'Actualizado' for fila in filas)


def test_error_despues_de_500_filas_revierte_la_importacion(app, auth_client, claro, monkeypatch):
    from blueprints import imports

    serializar = imports.safe_json_dumps

    def fallar_en_ultima_fila(data):
        if isinstance(data, dict) and data.get('Ticket Id') == 'QA-error-501':
            raise ValueError('Fallo simulado')
        return serializar(data)

    monkeypatch.setattr(imports, 'safe_json_dumps', fallar_en_ultima_fila)
    csv = 'Task Type,Ticket Id,Title\n' + ''.join(
        f'CM,QA-error-{indice},Registro\n' for indice in range(1, 502)
    )
    respuesta = importar(auth_client, csv)
    assert respuesta.status_code == 500
    assert respuesta.json['error'] == 'Fallo simulado'
    with app.app_context():
        assert not NucleusData.query.filter_by(proyecto_id=claro).filter(
            NucleusData.key_value.like('QA-error-%')
        ).count()


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
