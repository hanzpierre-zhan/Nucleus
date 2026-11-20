from datetime import timedelta
from db import db
from models import Usuario, DatosPersonalesUsuario
from services.perfil_personal import hoy_lima


def datos(fecha=None):
    return dict(primer_nombre='Ana', segundo_nombre='', apellido_paterno='Pérez',
                apellido_materno='Rojas', fecha_nacimiento=fecha or '1990-05-21')


def test_perfil_propio_y_fecha_invalida(app, auth_client):
    with auth_client.session_transaction() as ses:
        uid = ses['user_id']
    # Un id ajeno en el cuerpo nunca cambia la cuenta que se actualiza.
    respuesta = auth_client.post('/api/perfil-personal', json={**datos(), 'id': 999999})
    assert respuesta.status_code == 200
    with app.app_context():
        assert db.session.get(Usuario, uid).nombre == 'Ana Pérez Rojas'
        assert db.session.get(DatosPersonalesUsuario, uid).fecha_nacimiento.isoformat() == '1990-05-21'
    assert auth_client.post('/api/perfil-personal', json=datos('2030-02-30')).status_code == 400
    assert auth_client.post('/api/perfil-personal', json=datos((hoy_lima()+timedelta(days=1)).isoformat())).status_code == 400
    assert auth_client.get('/api/perfil-personal').json['perfil']['fecha_nacimiento'] == '1990-05-21'


def test_cumpleanos_sesion_y_privacidad(app, auth_client, cambiar_rol):
    hoy = hoy_lima()
    assert auth_client.post('/api/perfil-personal', json=datos(f'1990-{hoy.month:02}-{hoy.day:02}')).status_code == 200
    assert auth_client.get('/api/perfil-personal').json['cumpleanos']
    assert auth_client.get('/cumpleanos').status_code == 200
    auth_client.post('/api/cumpleanos/visto')
    assert auth_client.get('/api/perfil-personal').json['cumpleanos'] == []
    cambiar_rol(auth_client, 'supervisor')
    pagina = auth_client.get('/cumpleanos')
    assert pagina.status_code == 200
    assert b'Fecha de nacimiento</th>' not in pagina.data
    assert auth_client.get('/api/perfil-personal/usuario/1').status_code == 403


def test_sin_sesion(client):
    assert client.get('/api/perfil-personal').status_code in (302, 401)


def test_alta_admin_con_perfil(app, auth_client):
    respuesta = auth_client.post('/api/admin/usuario', json={**datos(), 'username':'perfil_nuevo',
        'password':'prueba123', 'rol':'supervisor', 'proyectos':[]})
    assert respuesta.status_code == 200
    uid = respuesta.json['id']
    with app.app_context():
        assert db.session.get(DatosPersonalesUsuario, uid).apellido_paterno == 'Pérez'
    assert auth_client.get('/api/perfil-personal/usuario/'+str(uid)).json['primer_nombre'] == 'Ana'
    with app.app_context():
        db.session.get(Usuario, uid).rol = 'eliminado'
        db.session.commit()
    assert auth_client.get('/api/perfil-personal/usuario/'+str(uid)).status_code == 404
