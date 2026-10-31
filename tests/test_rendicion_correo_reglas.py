"""Reglas del correo de aprobación en la validación de Rendición."""
import io
import json

import pytest

from blueprints.rendicion import _requiere_correo_validacion
from db import db
from models import NucleusData, RendicionCorreo
from test_rendicion_presupuesto_cotizacion import escenarios  # noqa: F401  (fixture)


def _row(presupuesto, gasto, tiempo=''):
    return {'Tipo de presupuesto': presupuesto, 'Tipo de gasto': gasto, 'TIEMPO DE RESPUESTA': tiempo}


@pytest.mark.parametrize('presupuesto,gasto,tiempo,esperado', [
    # REFACTURABLE: solo «Menor a 4 horas» exige correo.
    ('REFACTURABLE', 'Material', 'Menor a 4 horas', True),
    ('REFACTURABLE', 'Material', 'Mayor a 4 horas', False),
    ('REFACTURABLE', 'Material', 'Atención Continua', False),
    ('REFACTURABLE', 'Material', 'No aplica', False),
    ('REFACTURABLE', 'Material', '', True),
    # Gastos exentos: nunca piden correo.
    ('REFACTURABLE', 'VIÁTICOS', 'Menor a 4 horas', False),
    ('REFACTURABLE', 'PASAJE', 'Menor a 4 horas', False),
    ('REFACTURABLE', 'VIÁTICOS, PASAJE', 'Menor a 4 horas', False),
    ('REFACTURABLE', 'Peaje', 'Menor a 4 horas', False),
    ('REFACTURABLE', 'Hospedaje', 'Menor a 4 horas', False),
    # GASTO COBRA: depende del gasto, no del tiempo.
    ('GASTO COBRA', 'Material', 'Menor a 4 horas', True),
    ('GASTO COBRA', 'Material', 'No aplica', True),
    ('GASTO COBRA', 'Material', 'Atención Continua', True),
    ('GASTO COBRA', 'Acarreo de ge ducati', '', True),
    ('GASTO COBRA', 'Peaje, Material', '', True),
    ('GASTO COBRA', '', '', True),
    ('GASTO COBRA', 'Peaje', '', False),
    ('GASTO COBRA', 'PASAJE', '', False),
    ('GASTO COBRA', 'VIÁTICOS, PEAJE, PASAJE, HOSPEDAJE', '', False),
    # Otros presupuestos no piden correo.
    ('OTRO', 'Material', '', False),
])
def test_requiere_correo_por_presupuesto_gasto_y_tiempo(presupuesto, gasto, tiempo, esperado):
    row = _row(presupuesto, gasto, tiempo)
    assert _requiere_correo_validacion(row, tiempo) is esperado


def test_la_subida_ignora_el_tiempo_guardado_porque_aun_no_se_eligio():
    row = _row('REFACTURABLE', 'Material', 'No aplica')
    assert _requiere_correo_validacion(row) is False
    assert _requiere_correo_validacion(row, '') is True


def test_acentos_y_mayusculas_no_cambian_la_regla():
    assert _requiere_correo_validacion(_row('refacturable', 'viaticos', 'MENOR A 4 HORAS'), 'MENOR A 4 HORAS') is False
    assert _requiere_correo_validacion(_row('Refacturable', 'MATERIAL', 'atención continua'), 'atención continua') is False


def _preparar(app, escenarios, presupuesto, gasto):
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=escenarios, key_value='PRES-ACTUAL').one()
        datos = json.loads(fila.data_json)
        datos.update({'Tipo de presupuesto': presupuesto, 'Tipo de gasto': gasto,
                      'N° COTIZACION': 'PRES-2026-001'})
        fila.data_json = json.dumps(datos)
        db.session.commit()


@pytest.mark.parametrize('tiempo,esperado', [
    ('No aplica', 200), ('Mayor a 4 horas', 200), ('Atención Continua', 200), ('Menor a 4 horas', 400),
])
def test_refacturable_con_material_solo_pide_correo_con_menor_a_4_horas(app, auth_client, escenarios, tiempo, esperado):
    _preparar(app, escenarios, 'REFACTURABLE', 'Material')
    respuesta = auth_client.post('/api/rendicion/accion', json={
        'key': 'PRES-ACTUAL', 'accion': 'validar', 'tiempo': tiempo,
        'cotizacion': 'PRES-2026-001', 'presupuesto': '800.00'})
    assert respuesta.status_code == esperado, respuesta.json
    if esperado == 400:
        assert 'correo' in respuesta.json['error'].lower()


def test_gasto_cobra_con_material_sigue_pidiendo_correo_con_no_aplica(app, auth_client, escenarios):
    _preparar(app, escenarios, 'GASTO COBRA', 'Material')
    respuesta = auth_client.post('/api/rendicion/accion', json={
        'key': 'PRES-ACTUAL', 'accion': 'validar', 'tiempo': 'No aplica'})
    assert respuesta.status_code == 400, respuesta.json
    assert 'correo' in respuesta.json['error'].lower()


def test_gasto_cobra_con_pasaje_no_pide_correo(app, auth_client, escenarios):
    _preparar(app, escenarios, 'GASTO COBRA', 'PASAJE')
    respuesta = auth_client.post('/api/rendicion/accion', json={
        'key': 'PRES-ACTUAL', 'accion': 'validar', 'tiempo': 'No aplica'})
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json['newData']['ESTADO'] == 'VALIDADO'


def test_subir_correo_no_se_bloquea_por_el_tiempo_guardado(app, auth_client, escenarios):
    """Si vuelve a Validación con «No aplica» guardado y eligen «Menor a 4 horas»,
    el adjunto debe poder subirse aunque el tiempo antiguo no lo pidiera."""
    _preparar(app, escenarios, 'REFACTURABLE', 'Material')
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=escenarios, key_value='PRES-ACTUAL').one()
        datos = json.loads(fila.data_json)
        datos['TIEMPO DE RESPUESTA'] = 'No aplica'
        fila.data_json = json.dumps(datos)
        db.session.commit()
        origen_id = fila.id
    carga = auth_client.post('/api/rendicion/subir_correo', data={
        'key': 'PRES-ACTUAL', 'correo': (io.BytesIO(b'correo de prueba'), 'aprobacion.msg')})
    assert carga.status_code == 200, carga.json
    with app.app_context():
        RendicionCorreo.query.filter_by(origen_id=origen_id).delete()
        db.session.commit()
