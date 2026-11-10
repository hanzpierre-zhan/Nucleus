import io
import json

import pytest
from openpyxl import load_workbook

from db import db
from models import NucleusData, Proyecto


@pytest.fixture
def persona(app):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        fila = NucleusData(proyecto_id=pid, key_value='VN-71234567', data_json=json.dumps(
            {'DOCUMENTO': 'VN-71234567', 'TECNICO': 'Prueba Vista', 'ESTADO': 'ACTIVO', 'PROYECTO': 'FLM - CLARO', 'CELULAR': '900000001'}))
        db.session.add(fila); db.session.commit()
        fid = fila.id
    yield fid
    with app.app_context():
        NucleusData.query.filter_by(id=fid).delete(); db.session.commit()


def test_lista_editar_y_exportar_dataper(app, auth_client, persona):
    assert auth_client.get('/vista/dataper/').status_code == 200
    datos = auth_client.get('/api/vista/dataper/lista').json
    fila = next(f for f in datos['filas'] if f['id'] == persona)
    assert fila['pestana'] == 'CLARO' and fila['datos']['TECNICO'] == 'Prueba Vista'
    # DOCUMENTO siempre es la primera columna, aunque el diseño guardado la oculte.
    with app.app_context():
        from models import AppConfig
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        layout = AppConfig(proyecto_id=pid, clave='column_layout', valor=json.dumps([{'field': 'TECNICO'}, {'field': 'DOCUMENTO', 'visible': False}]))
        db.session.add(layout); db.session.commit()
        lid = layout.id
    try:
        assert auth_client.get('/api/vista/dataper/lista').json['columnas'][0] == 'DOCUMENTO'
    finally:
        with app.app_context():
            AppConfig.query.filter_by(id=lid).delete(); db.session.commit()
    # Otra vista abierta cambia el módulo de la sesión: guardar igual va a Dataper.
    auth_client.get('/vista/material/')
    r = auth_client.post('/api/vista/dataper/actualizar', json={'key': 'VN-71234567', 'field': 'CELULAR', 'value': '911111111'})
    assert r.status_code == 200, r.json
    with app.app_context():
        assert json.loads(db.session.get(NucleusData, persona).data_json)['CELULAR'] == '911111111'
    # Cesar y reactivar: solo ACTIVO o CESADO.
    assert auth_client.post('/api/vista/dataper/actualizar', json={'key': 'VN-71234567', 'field': 'ESTADO', 'value': 'CESADO'}).status_code == 200
    assert auth_client.post('/api/vista/dataper/actualizar', json={'key': 'VN-71234567', 'field': 'ESTADO', 'value': 'OTRO'}).status_code == 400
    assert auth_client.post('/api/vista/dataper/actualizar', json={'key': 'VN-71234567', 'field': 'ESTADO', 'value': 'ACTIVO'}).status_code == 200
    # Celular: 9 dígitos sin espacios; departamento: uno del Perú (con su nombre oficial).
    act = lambda campo, valor: auth_client.post('/api/vista/dataper/actualizar', json={'key': 'VN-71234567', 'field': campo, 'value': valor})
    assert act('CELULAR', '988 142 044').status_code == 200
    assert act('CELULAR', '12345').status_code == 400
    assert act('DEPARTAMENTO', 'junin').status_code == 200
    assert act('DEPARTAMENTO', 'Narnia').status_code == 400
    with app.app_context():
        guardado = json.loads(db.session.get(NucleusData, persona).data_json)
    assert guardado['CELULAR'] == '988142044' and guardado['DEPARTAMENTO'] == 'Junín'
    assert act('CELULAR', '911111111').status_code == 200
    libro = load_workbook(io.BytesIO(auth_client.post('/api/vista/dataper/exportar',
                                                      json={'ids': [persona], 'columnas': ['TECNICO', 'CELULAR']}).data))
    assert [c.value for c in libro.active[2]] == ['VN-71234567', 'Prueba Vista', '911111111']


def test_modulo_inexistente_y_usuarios(auth_client):
    assert auth_client.get('/vista/otra/').status_code == 404
    assert auth_client.get('/vista/usuarios/').status_code == 200
    usuarios = auth_client.get('/api/vista/usuarios/lista').json['usuarios']
    assert usuarios and {'id', 'username', 'rol', 'proyectos'} <= set(usuarios[0])
