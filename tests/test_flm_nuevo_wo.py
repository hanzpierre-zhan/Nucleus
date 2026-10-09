import json

import pytest

from db import db
from models import Proyecto, NucleusData
from services.utilidades import get_menu_proyectos


@pytest.mark.parametrize('nombre', ['FLM - CLARO', 'FLM - INTEGRATEL', 'FLM - ENTEL'])
def test_nuevo_wo_en_modulo_independiente(app, auth_client, nombre):
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre=nombre).one()
        pid = proyecto.id
    auth_client.get(f'/switch_project/{pid}')
    pagina = auth_client.get('/')
    assert pagina.status_code == 200
    assert b'onclick="aniadirRegistroWO()"' in pagina.data
    assert b'FLM - CLARO y INTEGRATEL' not in pagina.data
    respuesta = auth_client.post('/api/rows/add', json={'key': 'TEST-WO-FLM', 'data': {}})
    assert respuesta.status_code == 200, respuesta.json
    with app.app_context():
        registro = NucleusData.query.filter_by(proyecto_id=pid, key_value='TEST-WO-FLM').one()
        assert json.loads(registro.data_json)['Número de WO'] == 'TEST-WO-FLM'
        db.session.delete(registro)
        db.session.commit()


def test_modulo_combinado_no_se_crea_ni_se_muestra(app):
    with app.app_context():
        assert Proyecto.query.filter_by(nombre='FLM - CLARO y INTEGRATEL').first() is None
        legado = Proyecto(nombre='FLM - CLARO y INTEGRATEL')
        db.session.add(legado)
        db.session.commit()
        try:
            assert legado not in get_menu_proyectos(1, 'zeno')
        finally:
            db.session.delete(legado)
            db.session.commit()


@pytest.mark.parametrize('nombre', ['FLM - CLARO', 'FLM - INTEGRATEL'])
def test_contrata_no_puede_crear_wo(app, auth_client, nombre):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre=nombre).one().id
    with auth_client.session_transaction() as sesion:
        sesion['current_proyecto_id'] = pid
        sesion['current_proyecto_nombre'] = nombre
        sesion['rol'] = 'contrata'
    respuesta = auth_client.post('/api/rows/add', json={'key': 'WO-NO-PERMITIDO'})
    assert respuesta.status_code == 403


def test_sesion_antigua_sale_del_modulo_combinado(auth_client):
    with auth_client.session_transaction() as sesion:
        sesion['current_proyecto_nombre'] = 'FLM - CLARO y INTEGRATEL'
    respuesta = auth_client.get('/', follow_redirects=True)
    assert respuesta.status_code == 200
    with auth_client.session_transaction() as sesion:
        assert sesion['current_proyecto_nombre'] != 'FLM - CLARO y INTEGRATEL'


@pytest.mark.parametrize('nombre', ['FLM - CLARO', 'FLM - INTEGRATEL'])
def test_wo_pendiente_codigo_permanente_y_asignacion(app, auth_client, nombre):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre=nombre).one().id
    auth_client.get('/switch_project/%s' % pid)
    respuesta = auth_client.post('/api/rows/add', json={'key': '', 'data': {}})
    assert respuesta.status_code == 200, respuesta.json
    codigo = respuesta.json['key']
    assert codigo.startswith('CI-')
    with app.app_context():
        registro = NucleusData.query.filter_by(proyecto_id=pid, key_value=codigo).one()
        origen_id = registro.id
        datos = json.loads(registro.data_json)
        assert datos['CODIGO INTERNO'] == codigo
        assert datos['Número de WO'] == ''
        assert datos['_WO_PENDIENTE'] is True
    try:
        nueva = auth_client.post('/api/rows/edit_key', json={'old_key': codigo, 'new_key': 'CM-PENDIENTE-TEST'})
        assert nueva.status_code == 200, nueva.json
        with app.app_context():
            registro = db.session.get(NucleusData, origen_id)
            datos = json.loads(registro.data_json)
            assert datos['CODIGO INTERNO'] == codigo
            assert datos['Número de WO'] == 'CM-PENDIENTE-TEST'
            assert datos['_WO_PENDIENTE'] is False
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=origen_id).delete();db.session.commit()
