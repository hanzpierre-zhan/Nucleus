import json
from db import db
from models import Proyecto, NucleusData


def test_refacturable_solo_cotizaciones_aprobadas(app, auth_client):
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        filas = []
        for indice, estado in enumerate(['Aprobado', 'Atendido', 'En Aprobación', 'Cancelado']):
            fila = NucleusData(proyecto_id=proyecto.id, key_value='REF-TEST-' + str(indice), data_json=json.dumps({'N° COTIZACION': 'REF-TEST-' + str(indice), 'ESTADO COTIZACION': estado, 'GESTOR': 'gestor prueba', 'SUB TOTAL + FEE': '120.00', 'NUMERO WO': 'CM-123'}))
            db.session.add(fila)
            filas.append(fila)
        db.session.commit()
        ids = [fila.id for fila in filas]
    try:
        respuesta = auth_client.get('/refacturable/api/registros')
        assert respuesta.status_code == 200
        datos = {fila['id']: fila for fila in respuesta.json['registros']}
        assert ids[0] in datos and ids[1] in datos
        assert ids[2] not in datos and ids[3] not in datos
        assert datos[ids[0]]['numero_wo'] == 'CM-123'
        assert datos[ids[0]]['monto_hw'] == '120.00'
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


import pytest
from models import RefacturableDetalle


@pytest.fixture
def cot_aprobada(app):
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        registro = NucleusData(proyecto_id=proyecto.id, key_value='REF-MONTO-TEST', data_json=json.dumps({'ESTADO COTIZACION': 'Aprobado', 'SUB TOTAL + FEE': '120.35'}))
        db.session.add(registro)
        db.session.commit()
        origen_id = registro.id
    yield origen_id
    with app.app_context():
        RefacturableDetalle.query.filter_by(origen_id=origen_id).delete()
        NucleusData.query.filter_by(id=origen_id).delete()
        db.session.commit()


def test_monto_cobra_manual_margen_derivado_sin_cambiar_origen(app, auth_client, cot_aprobada):
    ruta = '/refacturable/api/registros/%s' % cot_aprobada
    respuesta = auth_client.patch(ruta, json={'monto_cobra': '200,50'})
    assert respuesta.status_code == 200
    registro = respuesta.json['registro']
    assert registro['monto_cobra'] == '200.50'
    assert registro['monto_hw'] == '120.35'
    assert registro['margen'] == '80.15'
    with app.app_context():
        origen = db.session.get(NucleusData, cot_aprobada)
        datos = json.loads(origen.data_json)
        assert datos == {'ESTADO COTIZACION': 'Aprobado', 'SUB TOTAL + FEE': '120.35'}
        datos['SUB TOTAL + FEE'] = '130.35'
        origen.data_json = json.dumps(datos)
        db.session.commit()
    guardado = next(r for r in auth_client.get('/refacturable/api/registros').json['registros'] if r['id'] == cot_aprobada)
    assert guardado['monto_cobra'] == '200.50'
    assert guardado['margen'] == '70.15'
    assert auth_client.patch(ruta, json={'monto_cobra': '0'}).json['registro']['margen'] == '-130.35'
    assert auth_client.patch(ruta, json={'monto_cobra': ''}).json['registro']['margen'] == ''


@pytest.mark.parametrize('cambios', [
    {'monto_hw': '500'}, {'margen': '500'}, {'monto_cobra': '-1'},
    {'monto_cobra': 'NaN'}, {'monto_cobra': 'abc'}, {'monto_cobra': {}},
])
def test_refacturable_valida_montos_y_campos_derivados(auth_client, cot_aprobada, cambios):
    assert auth_client.patch('/refacturable/api/registros/%s' % cot_aprobada, json=cambios).status_code == 400


def test_refacturable_impide_guardar_si_aprobacion_se_retiro(app, auth_client, cot_aprobada):
    with app.app_context():
        registro = db.session.get(NucleusData, cot_aprobada)
        registro.data_json = json.dumps({'ESTADO COTIZACION': 'Cancelado'})
        db.session.commit()
    assert auth_client.patch('/refacturable/api/registros/%s' % cot_aprobada, json={'monto_cobra': '200'}).status_code == 409


def test_refacturable_renderiza_montos_y_controles(auth_client):
    respuesta = auth_client.get('/refacturable/')
    assert respuesta.status_code == 200
    assert b'name="codigo_ajb_ejb"' in respuesta.data
    assert b'name="estado_liquidacion"' in respuesta.data
    assert b'id="ref-pagination"' in respuesta.data
    assert b'actualmente en construcci' not in respuesta.data
