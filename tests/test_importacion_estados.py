import io
import json
import pytest
from db import db
from models import Proyecto, NucleusData, AppConfig
from services.importacion_estados import cancelado


@pytest.mark.parametrize('proyecto,clave,estado',[
    ('FLM - CLARO','Ticket Id','Task Status'),
    ('FLM - INTEGRATEL','Task Id','Task Status'),
    ('FLM - ENTEL','Número de WO','Estado de la tarea (WO State)'),
    ('FLM - PEXT','Numero de WO','Estado de la tarea'),
])
def test_canceled_actualiza_existente_y_omite_nuevo(app,auth_client,proyecto,clave,estado):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre=proyecto).one().id
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='consolidation_config').first()
        anterior=cfg.valor if cfg else None
        if not cfg:
            cfg=AppConfig(proyecto_id=pid,clave='consolidation_config');db.session.add(cfg)
        cfg.valor=json.dumps({'auto_consolidate_missing':True})
        row=NucleusData(proyecto_id=pid,key_value='QA-CANCEL-EXISTE',data_json=json.dumps({estado:'Running','GESTOR':'Conservar','_EVIDENCIA_INICIO':'["/foto.jpg"]'}))
        db.session.add(row);db.session.commit();rid=row.id
    auth_client.get('/switch_project/%s'%pid)
    try:
        csv=f'{clave},{estado}\nQA-CANCEL-EXISTE, Canceled \nQA-CANCEL-NUEVO,cAnCeLeD\nQA-CANCEL-ACTIVO,Running\n'
        r=auth_client.post('/api/import/process',data={'type':'base','file':(io.BytesIO(csv.encode()),'datos.csv')})
        assert r.status_code==200,r.json
        assert r.json['added']==1 and r.json['ignored_canceled']==1 and r.json['updated_canceled']==1
        with app.app_context():
            guardado = json.loads(db.session.get(NucleusData,rid).data_json)
            assert guardado[estado]=='Canceled'
            assert guardado['GESTOR']=='Conservar' and guardado['_EVIDENCIA_INICIO']=='["/foto.jpg"]'
            assert not NucleusData.query.filter_by(proyecto_id=pid,key_value='QA-CANCEL-NUEVO').first()
        # Un archivo completamente cancelado tampoco consolida los activos.
        csv=f'{clave},{estado}\nQA-CANCEL-EXISTE,Canceled\n'
        r=auth_client.post('/api/import/process',data={'type':'base','file':(io.BytesIO(csv.encode()),'datos.csv')})
        assert r.status_code==200,r.json
        assert r.json['added']==r.json['updated']==r.json['consolidated']==0
        with app.app_context():
            assert NucleusData.query.filter_by(proyecto_id=pid,key_value='QA-CANCEL-ACTIVO').first()
        csv=f'{clave},{estado}\nQA-CANCEL-EXISTE,Running\nQA-CANCEL-ACTIVO,Running\n'
        r=auth_client.post('/api/import/process',data={'type':'base','file':(io.BytesIO(csv.encode()),'datos.csv')})
        assert r.status_code==200,r.json
        with app.app_context():
            assert json.loads(db.session.get(NucleusData,rid).data_json)[estado]=='Running'
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.key_value.like('QA-CANCEL-%')).delete(synchronize_session=False)
            cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='consolidation_config').one()
            if anterior is None:db.session.delete(cfg)
            else:cfg.valor=anterior
            db.session.commit()


def test_estado_solo_en_flm_y_prioridad_origen():
    assert not cancelado({'Task Status':'Canceled'},'Cotizaciones')
    assert not cancelado({'Task Status':'Running','Estado de la tarea (WO State)':'Canceled'},'FLM - CLARO')
    assert cancelado({'ESTADO DE LA TAREA':' Canceled '},'PEXT')


def test_importar_mas_de_5000_registros(app,auth_client):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
    auth_client.get('/switch_project/%s'%pid)
    try:
        csv='Ticket Id,Task Status\n'+''.join(f'QA-MAS5000-{i},Running\n' for i in range(5001))
        r=auth_client.post('/api/import/process',data={'type':'base','file':(io.BytesIO(csv.encode()),'datos.csv')})
        assert r.status_code==200,r.json
        assert r.json['added']==5001
        with app.app_context():
            assert NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.key_value.like('QA-MAS5000-%')).count()==5001
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.key_value.like('QA-MAS5000-%')).delete(synchronize_session=False)
            db.session.commit()
