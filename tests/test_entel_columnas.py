import json

from db import db
from models import Proyecto, AppConfig, NucleusData
from migrations.entel_columnas import COLUMNAS, ORIGEN, RESPALDO, VERSION, instalar, preparar


def test_recupera_visibilidad_orden_anchos_e_historicas():
    schema=['Nombre de Site','Columna propia']
    layout=[{'field':'Nombre de Site','visible':False,'width':320},
            {'field':'Columna propia','visible':False,'width':140}]
    backup={'quitadas_schema':['BITACORA HISTORICA'],
            'column_layout':[{'field':'BITACORA HISTORICA','visible':False,'width':280}]}
    new_schema,new_layout=preparar(schema,layout,backup)
    assert set(schema+COLUMNAS+['BITACORA HISTORICA']).issubset(new_schema)
    assert new_layout[:2][0]=={'field':'Nombre de Site','visible':True,'width':320}
    assert new_layout[1]==layout[1]
    historical=next(c for c in new_layout if c['field']=='BITACORA HISTORICA')
    assert historical['visible'] and historical['width']==280
    assert len({c['field'] for c in new_layout})==len(new_layout)


def test_migracion_solo_config_respaldo_e_idempotencia(app):
    with app.app_context():
        proyecto=Proyecto.query.filter_by(nombre='FLM - ENTEL').one()
        previos={c.clave:c.valor for c in AppConfig.query.filter_by(proyecto_id=proyecto.id)}
        original_rows=[(r.id,r.data_json) for r in NucleusData.query.order_by(NucleusData.id)]
        try:
            for key in (VERSION,RESPALDO):
                AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=key).delete()
            for key,value in [('app_schema','["Nombre de Site"]'),
                              ('column_layout','[{"field":"Nombre de Site","visible":false,"width":320}]'),
                              (ORIGEN,json.dumps({'quitadas_schema':['Campo histórico'],'column_layout':[]}))]:
                c=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=key).first()
                if c:c.valor=value
                else:db.session.add(AppConfig(proyecto_id=proyecto.id,clave=key,valor=value))
            db.session.commit()
            assert instalar() is True
            backup=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=RESPALDO).one()
            assert json.loads(backup.valor)['app_schema']=='["Nombre de Site"]'
            assert [(r.id,r.data_json) for r in NucleusData.query.order_by(NucleusData.id)]==original_rows
            layout=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave='column_layout').one()
            saved=json.loads(layout.valor);saved[0]['visible']=False
            layout.valor=json.dumps(saved);db.session.commit()
            assert instalar() is False
            assert json.loads(layout.valor)[0]['visible'] is False
        finally:
            AppConfig.query.filter_by(proyecto_id=proyecto.id).delete()
            db.session.add_all([AppConfig(proyecto_id=proyecto.id,clave=k,valor=v) for k,v in previos.items()])
            db.session.commit()
