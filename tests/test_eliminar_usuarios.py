from datetime import date

import pytest
from sqlalchemy import event, text
from werkzeug.security import check_password_hash, generate_password_hash

from config import TestingConfig
from db import db
from models import (AccesoEspacio, AccesoProyecto, AsistenciaCambio, AsistenciaDiaria,
                    AuditoriaEspacio, ConformidadUsuario, CuentaEspacio, HistorialCambios,
                    NucleusData, PerfilEspacio, Proyecto, Usuario)


@pytest.fixture
def cuentas_fk(tmp_path):
    from app import create_app

    class Config(TestingConfig):
        EVIDENCIA_DIR = str(tmp_path / 'evidencia')
        SQLALCHEMY_ENGINE_OPTIONS = {}

        @staticmethod
        def get_sqlalchemy_uri():
            return 'sqlite:///' + (tmp_path / 'cuentas.db').as_posix()

    app = create_app(Config)
    with app.app_context():
        db.session.remove()
        db.engine.dispose()

        @event.listens_for(db.engine, 'connect')
        def activar_fk(conn, _):
            conn.execute('PRAGMA foreign_keys=ON')

        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        actor = Usuario(username='retirar-prueba', nombre='Operador retirado',
                        password_hash=generate_password_hash('clave-prueba'), rol='supervisor')
        db.session.add(actor); db.session.flush()
        uid = actor.id
        ids = {p.nombre: p.id for p in Proyecto.query.all()}
        admin = Usuario.query.filter_by(rol='zeno').first().id
        db.session.add(ConformidadUsuario(usuario_id=uid, version='2026-10-09'))
        db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=ids['FLM - ENTEL'], restricciones='{}'))
        db.session.add(CuentaEspacio(usuario_id=uid))
        perfil = PerfilEspacio(nombre='Perfil retiro', permisos_json='{}')
        db.session.add(perfil); db.session.flush()
        db.session.add(AccesoEspacio(usuario_id=uid, proyecto_id=ids['FLM - ENTEL'], perfil_id=perfil.id))
        persona = NucleusData(proyecto_id=ids['Dataper'], key_value='PERSONA-RETIRO', data_json='{}')
        db.session.add(persona); db.session.flush()
        asistencia = AsistenciaDiaria(personal_id=persona.id, proyecto_id=ids['FLM - ENTEL'], fecha=date(2026, 10, 18),
                                     estado='presente', nombre='Persona', documento='123', actualizado_por=uid)
        db.session.add(asistencia); db.session.flush()
        db.session.add(AsistenciaCambio(asistencia_id=asistencia.id, usuario_id=uid, nuevo_json='{}'))
        db.session.add(AuditoriaEspacio(usuario_id=uid, accion='prueba', detalle_json='{}'))
        db.session.add(HistorialCambios(usuario_id=uid, username=actor.username,
                                       proyecto_id=ids['FLM - ENTEL'], key_value='WO-RETIRO', campo_modificado='ESTADO'))
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(user_id=admin, rol='zeno', username='zeno', current_proyecto_id=ids['FLM - ENTEL'])
    yield app, client, uid, admin
    with app.app_context():
        db.session.remove(); db.engine.dispose()


def test_eliminar_con_conformidad_asistencia_y_auditoria_preserva_todas_las_fk(cuentas_fk):
    app, c, uid, _ = cuentas_fk
    response = c.delete('/api/admin/usuario', json={'id': uid})
    assert response.status_code == 200 and response.json['success']
    with app.app_context():
        u = db.session.get(Usuario, uid)
        assert u.rol == 'eliminado' and u.nombre == 'Operador retirado'
        assert u.username == 'retirar-prueba' and not check_password_hash(u.password_hash, 'clave-prueba')
        assert not AccesoProyecto.query.filter_by(usuario_id=uid).count()
        assert not AccesoEspacio.query.filter_by(usuario_id=uid).count()
        assert db.session.get(CuentaEspacio, uid) is None
        assert db.session.get(ConformidadUsuario, uid)
        assert AsistenciaDiaria.query.filter_by(actualizado_por=uid).count() == 1
        assert AsistenciaCambio.query.filter_by(usuario_id=uid).count() == 1
        assert AuditoriaEspacio.query.filter_by(usuario_id=uid).count() == 1
        h = HistorialCambios.query.filter_by(usuario_id=uid).one()
        assert h.username == 'retirar-prueba'
        assert not db.session.execute(text('PRAGMA foreign_key_check')).all()
    assert c.delete('/api/admin/usuario', json={'id': uid}).status_code == 200
    assert '<b>Operador retirado</b>' not in c.get('/usuarios').text
    nueva = c.post('/api/admin/usuario', json={'username': 'retirar-prueba', 'password': 'otra-clave', 'rol': 'supervisor'})
    assert nueva.status_code == 400  # El identificador histórico queda reservado.


def test_cuenta_retirada_no_reutiliza_sesion_ni_verificacion_pendiente(cuentas_fk):
    app, admin, uid, _ = cuentas_fk
    antiguo = app.test_client()
    with antiguo.session_transaction() as s:
        s.update(user_id=uid, username='retirar-prueba', rol='supervisor')
    pendiente = app.test_client()
    import time
    with pendiente.session_transaction() as s:
        s['legal_pending'] = {'user_id': uid, 'verified_at': time.time()}
    assert admin.delete('/api/admin/usuario', json={'id': uid}).status_code == 200
    assert antiguo.get('/api/wo/meta').status_code == 401
    assert pendiente.post('/login', data={'consent_step': '1', 'legal_accept': '1'}).status_code == 400
    login = app.test_client()
    login.post('/login', data={'username': 'retirar-prueba', 'password': 'clave-prueba'})
    with login.session_transaction() as s:
        assert not s.get('user_id') and not s.get('legal_pending')


def test_eliminar_no_permite_borrarse_a_si_mismo_y_valida_id(cuentas_fk):
    _, c, _, admin = cuentas_fk
    assert c.delete('/api/admin/usuario', json={'id': admin}).status_code == 400
    for valor in (None, 'incorrecto', -1):
        assert c.delete('/api/admin/usuario', json={'id': valor}).status_code == 400
