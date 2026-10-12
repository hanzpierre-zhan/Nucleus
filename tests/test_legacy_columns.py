import json
from db import db
from models import AppConfig,NucleusData,Proyecto
from services.legacy_columns import clean_config,retired

def test_retirar_solo_columnas_antiguas():
    assert retired('SLA') and retired('SLA_Cumplimiento')
    assert not retired('FECHA INICIO') and not retired('ESTADO COTIZACION')
    value=json.dumps([{'field':'SLA'},{'field':'Fecha de creación','width':190},{'field':'SLA Cumplimiento'}])
    assert json.loads(clean_config('column_layout__depositos',value))==[{'field':'Fecha de creación','width':190}]
    assert clean_config('otros_datos',value)==value

def test_columnas_no_reaparecen_al_guardar_o_importar(app):
    with app.app_context():
        p=Proyecto.query.filter_by(nombre='FLM - CLARO').one()
        config=AppConfig(proyecto_id=p.id,clave='column_layout__legacy_test',valor=json.dumps([{'field':'SLA'},{'field':'Nombre de Site'}]))
        row=NucleusData(proyecto_id=p.id,key_value='LEGACY-COLUMNA-TEST',data_json=json.dumps({'SLA':'300','SLA Cumplimiento':'Activo','INICIO EJECUCION':'2026-10-12 09:00:00','ESTADO':'closed'}))
        db.session.add_all([config,row]);db.session.commit()
        assert json.loads(config.valor)==[{'field':'Nombre de Site'}]
        assert json.loads(row.data_json)=={'INICIO EJECUCION':'2026-10-12 09:00:00','ESTADO':'closed'}
        db.session.delete(config);db.session.delete(row);db.session.commit()
