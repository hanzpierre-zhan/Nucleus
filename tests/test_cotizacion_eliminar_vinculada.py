import json
import sqlite3
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db import db
from models import Proyecto,NucleusData,RefacturableDetalle,LiquidacionNumero,HistorialCambios


@pytest.fixture
def foreign_keys(app):
    with app.app_context():
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar()==1
        yield
        db.session.rollback()
        db.session.execute(text('PRAGMA foreign_keys=OFF'))
        db.session.commit()


def crear(pid,key):
    row=NucleusData(proyecto_id=pid,key_value=key,data_json=json.dumps({'N° COTIZACION':key,'ESTADO COTIZACION':'Aprobado','SUB TOTAL + FEE':'250'}))
    db.session.add(row);db.session.flush()
    detail=RefacturableDetalle(origen_id=row.id,data_json=json.dumps({'estado_liquidacion':'Pendiente','comentarios':'Conservar seguimiento'}),actualizado_por='qa')
    db.session.add_all([detail,LiquidacionNumero(origen_id=row.id)]);db.session.commit()
    return row.id


def test_elimina_cotizacion_y_respalda_detalle_sin_afectar_otros(app,auth_client,foreign_keys):
    pid=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    other=Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
    source=crear(pid,'DELETE-COT-LINK')
    untouched=crear(other,'DELETE-COT-LINK')
    auth_client.get(f'/switch_project/{pid}')
    response=auth_client.post('/api/rows/delete',json={'keys':['DELETE-COT-LINK']})
    assert response.status_code==200,response.json
    db.session.expire_all()
    assert db.session.get(NucleusData,source) is None
    assert db.session.get(RefacturableDetalle,source) is None
    assert db.session.get(NucleusData,untouched) is not None
    assert db.session.get(RefacturableDetalle,untouched) is not None
    assert LiquidacionNumero.query.filter_by(origen_id=source).one()
    history=HistorialCambios.query.filter_by(proyecto_id=pid,key_value='DELETE-COT-LINK',campo_modificado='_REGISTRO_ELIMINADO').one()
    saved=json.loads(history.valor_anterior)
    assert json.loads(saved['liquidacion_json'])['comentarios']=='Conservar seguimiento'
    assert json.loads(saved['registro_json'])['SUB TOTAL + FEE']=='250'
    assert saved['origen_id']==source
    assert not db.session.execute(text('PRAGMA foreign_key_check')).all()


def test_fallo_de_commit_revierte_origen_detalle_e_historial(app,auth_client,foreign_keys,monkeypatch):
    pid=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    source=crear(pid,'DELETE-COT-ROLLBACK')
    auth_client.get(f'/switch_project/{pid}')
    def fail_commit():
        raise IntegrityError('DELETE nucleus_data',{},sqlite3.IntegrityError('foreign key test'))
    with monkeypatch.context() as patch:
        patch.setattr(db.session,'commit',fail_commit)
        response=auth_client.post('/api/rows/delete',json={'keys':['DELETE-COT-ROLLBACK']})
    assert response.status_code==409
    assert 'No se eliminó ningún registro' in response.json['error']
    assert 'DELETE nucleus_data' not in response.json['error']
    assert db.session.get(NucleusData,source) is not None
    assert db.session.get(RefacturableDetalle,source) is not None
    assert HistorialCambios.query.filter_by(proyecto_id=pid,key_value='DELETE-COT-ROLLBACK',campo_modificado='_REGISTRO_ELIMINADO').count()==0


def test_eliminacion_sin_permiso_conserva_datos(app,auth_client,foreign_keys,cambiar_rol):
    pid=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    source=crear(pid,'DELETE-COT-PERMISO')
    auth_client.get(f'/switch_project/{pid}')
    cambiar_rol(auth_client,'gestor')
    response=auth_client.post('/api/rows/delete',json={'keys':['DELETE-COT-PERMISO']})
    assert response.status_code==403
    assert db.session.get(NucleusData,source) is not None
    assert db.session.get(RefacturableDetalle,source) is not None


def test_eliminacion_masiva_con_y_sin_detalle(app,auth_client,foreign_keys):
    pid=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    linked=crear(pid,'DELETE-COT-BULK-LINK')
    plain=NucleusData(proyecto_id=pid,key_value='DELETE-COT-BULK-PLAIN',data_json='{}')
    db.session.add(plain);db.session.commit();plain_id=plain.id
    auth_client.get(f'/switch_project/{pid}')
    response=auth_client.post('/api/rows/delete',json={'keys':['DELETE-COT-BULK-LINK','DELETE-COT-BULK-PLAIN','DELETE-COT-BULK-LINK','NO-EXISTE']})
    assert response.status_code==200,response.json
    db.session.expire_all()
    assert db.session.get(NucleusData,linked) is None
    assert db.session.get(NucleusData,plain_id) is None
    assert db.session.get(RefacturableDetalle,linked) is None
    assert HistorialCambios.query.filter(HistorialCambios.proyecto_id==pid,HistorialCambios.key_value.in_(['DELETE-COT-BULK-LINK','DELETE-COT-BULK-PLAIN']),HistorialCambios.campo_modificado=='_REGISTRO_ELIMINADO').count()==2
