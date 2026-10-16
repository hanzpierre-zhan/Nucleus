import json
from pathlib import Path
from db import db
from models import Proyecto, AppConfig
from services.columnas_fuente import instalar, presentar, VERSION
from services.legacy_columns import retired


def test_perfiles_columnas_iguales_al_origen(app):
    with app.app_context():
        perfiles=json.loads(Path('services/data/columnas_flm_v1.json').read_text(encoding='utf-8'))
        for nombre,perfil in perfiles.items():
            proyecto=Proyecto.query.filter_by(nombre=nombre).one()
            cfg={c.clave:c.valor for c in AppConfig.query.filter_by(proyecto_id=proyecto.id)}
            assert cfg['primary_key']==perfil['configuracion']['primary_key']
            esperado=[x for x in perfil['configuracion']['app_schema'] if not retired(x)]
            assert set(esperado).issubset(json.loads(cfg['app_schema']))
            assert [c['nombre'] for c in json.loads(cfg['manual_columns'])]==[c['nombre'] for c in perfil['configuracion']['manual_columns']]
            assert VERSION in cfg


def test_migracion_no_pisa_cambios_posteriores(app):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='column_layout').one()
        anterior=cfg.valor
        try:
            cfg.valor=json.dumps([{'field':'Task Id','visible':False}]);db.session.commit()
            instalar()
            assert json.loads(cfg.valor)==[{'field':'Task Id','visible':False}]
        finally:
            cfg.valor=anterior;db.session.commit()


def test_registro_antiguo_presenta_columnas_nuevas_sin_cambiarlo():
    original={'Número de WO':'CM-ANTERIOR','Nombre de Site':'Sitio','Estado de la tarea (WO State)':'closed','Departamento':'JUNIN','OTRO':'Conservar'}
    vista=presentar(original,'FLM - INTEGRATEL','CM-ANTERIOR')
    assert vista['Task Id']=='CM-ANTERIOR' and vista['Task Status']=='closed'
    assert vista['Site Id Name']=='Sitio' and vista['DEPARTAMENTO']=='JUNIN'
    assert vista['OTRO']=='Conservar' and 'Task Id' not in original
