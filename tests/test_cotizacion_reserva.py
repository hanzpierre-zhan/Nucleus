import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from db import db
from models import AccesoProyecto, AppConfig, NucleusData, Proyecto, Usuario
from services.cotizacion_numeracion import crear
from services.utilidades import ahora_peru


@pytest.fixture
def escenario(app):
    with app.app_context():
        proyectos = {p.nombre: p.id for p in Proyecto.query.all()}
        pid = proyectos['Cotizaciones']
        originales = {c.clave: c.valor for c in AppConfig.query.filter_by(proyecto_id=pid)
                      if c.clave in ('cotizacion_next_seq', 'cotizacion_next_order')}
        for clave in ('cotizacion_next_seq', 'cotizacion_next_order'):
            cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=clave).first()
            if cfg is None:
                cfg = AppConfig(proyecto_id=pid, clave=clave)
                db.session.add(cfg)
            cfg.valor = '9000201' if clave == 'cotizacion_next_seq' else '1'
        usuario = Usuario(username='numeracion-' + uuid4().hex[:10], rol='supervisor', password_hash='no-login')
        db.session.add(usuario); db.session.flush()
        uid, username = usuario.id, usuario.username
        for nombre in ('FLM - ENTEL', 'Cotizaciones'):
            db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=proyectos[nombre], restricciones='{}'))
        fecha = ahora_peru()
        visible = f'EN-{fecha.year}-{fecha.month:02d}-9000199'
        oculto = f'CL-{fecha.year}-{fecha.month:02d}-9000200'
        iniciales = {r.id for r in NucleusData.query.filter_by(proyecto_id=pid)}
        for key, cliente, orden in ((visible, 'ENTEL', '5'), (oculto, 'CLARO', '9000200')):
            db.session.add(NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps({
                'N° COTIZACION': key, 'N° ORDEN': orden, 'CLIENTE': cliente})))
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=uid, username=username, rol='supervisor', current_proyecto_id=pid,
                       current_proyecto_nombre='Cotizaciones')
    yield client, pid, fecha, visible, oculto
    with app.app_context():
        db.session.rollback()
        NucleusData.query.filter(NucleusData.proyecto_id == pid, ~NucleusData.id.in_(iniciales)).delete(synchronize_session=False)
        for clave in ('cotizacion_next_seq', 'cotizacion_next_order'):
            cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=clave).first()
            if clave in originales:
                cfg.valor = originales[clave]
            elif cfg:
                db.session.delete(cfg)
        AccesoProyecto.query.filter_by(usuario_id=uid).delete()
        db.session.delete(db.session.get(Usuario, uid))
        db.session.commit()


def test_usuario_restringido_recibe_numero_y_orden_globales_sin_ver_otro_cliente(app, escenario):
    client, pid, fecha, visible, oculto = escenario
    preview = client.get('/api/cotizacion/next_seq')
    assert preview.json['next'] == 9000201
    assert preview.headers['Cache-Control'] == 'no-store'
    # Hasta la clave que ya existe es solo una sugerencia en modo automático.
    response = client.post('/api/rows/add', json={'key': visible, 'data': {
        'CLIENTE': 'ENTEL', 'N° COTIZACION': visible, 'MOTIVO': 'Conservar texto'}})
    assert response.status_code == 200, response.json
    assert response.json['key'].endswith('9000201')
    assert response.json['orden'] == '9000201'
    assert client.post('/api/rows/update', json={'key': oculto, 'field': 'MOTIVO', 'value': 'no permitido'}).status_code == 404
    with app.app_context():
        datos = json.loads(NucleusData.query.filter_by(proyecto_id=pid, key_value=response.json['key']).one().data_json)
        assert datos['MOTIVO'] == 'Conservar texto'
        assert 'MOTIVO' not in json.loads(NucleusData.query.filter_by(proyecto_id=pid, key_value=oculto).one().data_json)


def test_dos_formularios_con_mismo_provisional_guardan_diferentes(escenario):
    client, _, fecha, _, _ = escenario
    preview = f'EN-{fecha.year}-{fecha.month:02d}-9000201'
    payload = {'key': preview, 'numeracion_modo': 'automatico', 'data': {'CLIENTE': 'ENTEL', 'N° COTIZACION': preview}}
    responses = [client.post('/api/rows/add', json=payload) for _ in range(2)]
    assert all(r.status_code == 200 for r in responses)
    assert [r.json['key'] for r in responses] == [preview, preview[:-1] + '2']


def test_manual_ocupado_no_se_cambia_sin_decision_y_ofrece_automatico(app, escenario):
    client, pid, fecha, _, _ = escenario
    payload = {'key': '', 'numeracion_modo': 'manual', 'data': {
        'CLIENTE': 'ENTEL', 'N° COTIZACION': f'EN-{fecha.year}-{fecha.month:02d}-9000200', 'MOTIVO': 'No perder'}}
    response = client.post('/api/rows/add', json=payload)
    assert response.status_code == 409
    assert response.json['code'] == 'COTIZACION_NUMERO_NO_DISPONIBLE'
    assert response.json['suggested'].endswith('9000201')
    assert response.json['datos_conservados'] is True
    payload['numeracion_modo'] = 'automatico'
    response = client.post('/api/rows/add', json=payload)
    assert response.status_code == 200
    with app.app_context():
        datos = json.loads(NucleusData.query.filter_by(proyecto_id=pid, key_value=response.json['key']).one().data_json)
        assert datos['MOTIVO'] == 'No perder'


def test_manual_disponible_se_respeta(escenario):
    client, _, _, _, _ = escenario
    response = client.post('/api/rows/add', json={'key': '', 'numeracion_modo': 'manual',
        'data': {'CLIENTE': 'ENTEL', 'N° COTIZACION': '9000250'}})
    assert response.status_code == 200
    assert response.json['key'].endswith('9000250')


@pytest.mark.parametrize('constraint,esperados', [('uq_cotizacion_orden', 2), ('fk_no_numeracion', 1)])
def test_reintenta_solo_conflicto_de_numeracion(app, escenario, monkeypatch, constraint, esperados):
    _, pid, fecha, _, _ = escenario
    with app.app_context():
        original = db.session.commit
        antes = NucleusData.query.filter_by(proyecto_id=pid).count()
        calls = []
        def commit():
            calls.append(1)
            if len(calls) == 1:
                raise IntegrityError('insert', {}, SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint)))
            return original()
        with monkeypatch.context() as m:
            m.setattr(db.session, 'commit', commit)
            if esperados == 1:
                with pytest.raises(IntegrityError):
                    crear(pid, 'EN', fecha, {'CLIENTE': 'ENTEL'})
            else:
                assert crear(pid, 'EN', fecha, {'CLIENTE': 'ENTEL'})['success']
        assert len(calls) == esperados
        assert NucleusData.query.filter_by(proyecto_id=pid).count() == antes + (1 if esperados == 2 else 0)
