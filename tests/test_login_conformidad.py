import time
import pytest
from werkzeug.security import generate_password_hash
from db import db
from models import Usuario, ConformidadUsuario


@pytest.fixture
def cuenta(app):
    with app.app_context():
        user = Usuario(username='consent-test', password_hash=generate_password_hash('test-pass'))
        db.session.add(user)
        db.session.commit()
        uid = user.id
    yield {'username': 'consent-test', 'password': 'test-pass'}, uid
    with app.app_context():
        ConformidadUsuario.query.filter_by(usuario_id=uid).delete()
        db.session.delete(db.session.get(Usuario, uid))
        db.session.commit()


def test_primer_acceso_exige_conformidad(client, cuenta):
    credenciales, uid = cuenta
    assert b'name="legal_accept"' not in client.get('/login').data
    respuesta = client.post('/login', data=credenciales)
    assert respuesta.status_code == 200
    assert b'name="legal_accept"' in respuesta.data
    with client.session_transaction() as sesion:
        assert 'user_id' not in sesion
    assert client.post('/login', data={'consent_step': '1'}).status_code == 400
    assert client.post('/login', data={'consent_step': '1', 'legal_accept': '1'}).status_code == 302


def test_recuerda_aceptacion_tras_logout_y_otro_navegador(app, client, cuenta):
    credenciales, uid = cuenta
    client.post('/login', data=credenciales)
    client.post('/login', data={'consent_step': '1', 'legal_accept': '1'})
    with app.app_context():
        aceptado = db.session.get(ConformidadUsuario, uid).aceptado_en
    client.get('/logout')
    for navegador in (client, app.test_client()):
        assert navegador.post('/login', data=credenciales).status_code == 302
        with navegador.session_transaction() as sesion:
            assert sesion['user_id'] == uid
    with app.app_context():
        assert db.session.get(ConformidadUsuario, uid).aceptado_en == aceptado


def test_otro_usuario_debe_aceptar(app, auth_client, cuenta):
    credenciales, uid = cuenta
    auth_client.get('/logout')
    respuesta = auth_client.post('/login', data=credenciales)
    assert b'name="legal_accept"' in respuesta.data
    with auth_client.session_transaction() as sesion:
        assert 'user_id' not in sesion


def test_no_acepta_sin_credenciales(client):
    assert client.post('/login', data={'consent_step': '1', 'legal_accept': '1'}).status_code == 400
    with client.session_transaction() as sesion:
        assert 'user_id' not in sesion


def test_verificacion_expirada(client, cuenta):
    credenciales, uid = cuenta
    client.post('/login', data=credenciales)
    with client.session_transaction() as sesion:
        sesion['legal_pending'] = {'user_id': uid, 'verified_at': time.time() - 301}
    assert client.post('/login', data={'consent_step': '1', 'legal_accept': '1'}).status_code == 400


@pytest.mark.parametrize('ruta', ['/privacidad', '/terminos', '/cookies'])
def test_politicas_publicas(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    assert respuesta.data.count(b'<title>') == 1
