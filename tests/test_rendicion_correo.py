import io
import json
import pytest
from db import db
from models import Proyecto, NucleusData

@pytest.fixture
def solicitud(app, auth_client, monkeypatch):
    import blueprints.rendicion as modulo
    monkeypatch.setattr(modulo, '_avisar_flujo', lambda *args: None)
    with app.app_context():
        p = Proyecto.query.filter_by(nombre='Rendicion').one()
        fila = NucleusData(proyecto_id=p.id, key_value='REND-CORREO-TEST', data_json=json.dumps({'ESTADO': 'PENDIENTE', 'TIPO DE PRESUPUESTO': 'REFACTURABLE'}))
        db.session.add(fila); db.session.commit()
        pid, origen_id = p.id, fila.id
    auth_client.get('/switch_project/%s' % pid)
    yield origen_id
    with app.app_context():
        NucleusData.query.filter_by(id=origen_id).delete(); db.session.commit()


def test_refacturable_requiere_correo_real_y_vinculado(app, auth_client, solicitud):
    payload = {'key': 'REND-CORREO-TEST', 'accion': 'validar', 'tiempo': 'Menor a 4 horas'}
    assert auth_client.post('/api/rendicion/accion', json=payload).status_code == 400
    payload['correo'] = '/inventado.msg'
    assert auth_client.post('/api/rendicion/accion', json=payload).status_code == 400
    carga = auth_client.post('/api/rendicion/subir_correo', data={'key': payload['key'], 'correo': (io.BytesIO(b'correo outlook prueba'), 'aprobacion.msg')})
    assert carga.status_code == 200
    assert auth_client.get(carga.json['url']).data == b'correo outlook prueba'
    respuesta = auth_client.post('/api/rendicion/accion', json=payload)
    assert respuesta.status_code == 200
    assert respuesta.json['newData']['ESTADO'] == 'VALIDADO'
    assert respuesta.json['newData']['ADJUNTO CORREO VALIDACION'] == carga.json['url']


def test_archivo_erroneo_no_permite_validar(auth_client, solicitud):
    respuesta = auth_client.post('/api/rendicion/subir_correo', data={'key': 'REND-CORREO-TEST', 'correo': (io.BytesIO(b'pdf'), 'archivo.pdf')})
    assert respuesta.status_code == 400


def test_no_refacturable_no_exige_correo(app, auth_client, solicitud):
    with app.app_context():
        fila = db.session.get(NucleusData, solicitud)
        fila.data_json = json.dumps({'ESTADO': 'PENDIENTE', 'TIPO DE PRESUPUESTO': 'NO REFACTURABLE'})
        db.session.commit()
    assert auth_client.post('/api/rendicion/accion', json={'key': 'REND-CORREO-TEST', 'accion': 'validar', 'tiempo': 'No aplica'}).status_code == 200
