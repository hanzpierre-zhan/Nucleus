"""Nucleus Mobile · Asistencia individual: con vehículo o a pie, con compañero o solo; foto con coordenadas, una vez por día."""
import io
import json
import re

import pytest
from PIL import Image

from db import db
from models import (AccesoProyecto, AsistenciaCambio, AsistenciaCuadrilla, AsistenciaDiaria, ClaveTecnico, NucleusData, Proyecto,
                    UbicacionMovil, Usuario)

DOC = '47770001'


@pytest.fixture
def cuadrilla(app, monkeypatch, tmp_path):
    from werkzeug.security import generate_password_hash
    monkeypatch.setitem(app.config, 'EVIDENCIA_DIR', str(tmp_path))
    monkeypatch.setitem(app.config, 'FORM_PRUEBAS_DIR', str(tmp_path / 'formularios'))
    monkeypatch.setitem(app.config, 'FORM_PRUEBAS_ENABLED', True)
    for clave in ('B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY'):
        monkeypatch.setitem(app.config, clave, '')
    monkeypatch.delenv('RENDER', raising=False)
    persona = lambda doc, nombre, cargo, proyecto='FLM - CLARO', estado='ACTIVO': NucleusData(
        proyecto_id=pid, key_value=doc, data_json=json.dumps({'DOCUMENTO': doc, 'TECNICO': nombre, 'ESTADO': estado, 'PROYECTO': proyecto,
                                                               'CARGO': cargo, 'SUPERVISOR': 'Sup Uno', 'DEPARTAMENTO': 'Lima', 'CELULAR': '999111222'}))
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        filas = [persona(DOC, 'Principal Uno', 'TECNICO ESPECIALISTA'), persona('47770002', 'Junior Dos', 'TECNICO JUNIOR'),
                 persona('47770003', 'Otro Tres', 'TECNICO'), persona('47770004', 'Entel Cuatro', 'JUNIOR', 'FLM - ENTEL'),
                 persona('47770005', 'Cesado Cinco', 'JUNIOR', estado='CESADO'), persona('47770006', 'Supervisora Seis', 'SUPERVISOR')]
        db.session.add_all(filas + [ClaveTecnico(documento=DOC, clave_hash=generate_password_hash('Clave-123'))])
        db.session.commit()
        ids = {json.loads(f.data_json)['TECNICO']: f.id for f in filas}
    cliente = app.test_client()
    token = re.search(rb'id="csrf" type="hidden" value="([^"]+)"', cliente.get('/form-pruebas/').data).group(1).decode()
    assert cliente.post('/form-pruebas/ingresar', json={'documento': DOC, 'clave': 'Clave-123'},
                        headers={'X-CSRF-Token': token}).status_code == 200
    with cliente.session_transaction() as s:
        token = s['form_csrf']
        s.pop('form_verificar_dataper')
    yield cliente, {'X-CSRF-Token': token, 'X-Ubicacion': '-12.0464,-77.0428,12', 'X-Dispositivo': 'cel-1'}, ids
    with app.app_context():
        AsistenciaCuadrilla.query.filter_by(documento=DOC).delete()
        UbicacionMovil.query.filter(UbicacionMovil.documento.like('4777000%')).delete(synchronize_session=False)
        NucleusData.query.filter(NucleusData.id.in_(ids.values())).delete(synchronize_session=False)
        ClaveTecnico.query.filter_by(documento=DOC).delete()
        db.session.commit()


def _foto():
    b = io.BytesIO(); Image.new('RGB', (800, 600), (40, 90, 160)).save(b, 'JPEG'); b.seek(0)
    return (b, 'cuadrilla.jpg')


def test_actualizar_dataper_en_mobile(app, cuadrilla):
    cli, h, ids = cuadrilla
    with cli.session_transaction() as sesion:
        sesion['form_verificar_dataper'] = True
    # Los nombres importados pueden contener espacios repetidos o no separables.
    with app.app_context():
        supervisor = db.session.get(NucleusData, ids['Supervisora Seis'])
        ficha = json.loads(supervisor.data_json)
        ficha['TECNICO'] = '  Supervisora\u00a0  Seis  '
        supervisor.data_json = json.dumps(ficha)
        db.session.commit()
    assert cli.get('/form-pruebas/').location.endswith('/form-pruebas/dataper')
    assert cli.get('/form-pruebas/asistencia').location.endswith('/form-pruebas/dataper')
    assert b'capture="user"' in cli.get('/form-pruebas/dataper').data
    datos = {
        'PRIMER NOMBRE': 'Juan', 'APELLIDO PATERNO': 'Pérez', 'APELLIDO MATERNO': 'López',
        'FECHA DE NACIMIENTO': '1998-07-03', 'CARGO': 'TÉCNICO JUNIOR',
        'SUPERVISOR': 'SUPERVISORA SEIS', 'CELULAR': '999111222',
        'NÚMERO DE EMERGENCIA': '988111222', 'CONTACTO DE EMERGENCIA': 'Ana Pérez',
        'DEPARTAMENTO': 'LIMA', 'PROVINCIA': 'Lima', 'DISTRITO': 'Lima',
    }
    csrf_header = {'X-CSRF-Token': h['X-CSRF-Token']}
    assert cli.post('/form-pruebas/dataper', headers=csrf_header, data=datos).status_code == 400
    assert cli.post('/form-pruebas/dataper', headers=csrf_header,
                    data={**datos, 'CARGO': 'SUPERVISOR', 'foto': _foto()}).status_code == 400
    assert cli.post('/form-pruebas/dataper', data={**datos, 'foto': _foto()}).status_code == 403
    assert cli.post('/form-pruebas/dataper', headers=csrf_header,
                    data={**datos, 'foto': _foto()}).status_code == 302
    with app.app_context():
        fila = db.session.get(NucleusData, ids['Principal Uno'])
        ficha = json.loads(fila.data_json)
        assert ficha['APELLIDO PATERNO'] == 'PÉREZ'
        assert ficha['DOCUMENTO'] == DOC and ficha['ESTADO'] == 'ACTIVO'
        assert ficha['PROYECTO'] == 'FLM - CLARO'
        assert ficha['CARGO'] == 'TÉCNICO JUNIOR'
    assert cli.get('/form-pruebas/').location.endswith('/form-pruebas/asistencia')
    assert cli.get('/form-pruebas/dataper/foto').mimetype == 'image/jpeg'
    assert app.test_client().get('/form-pruebas/dataper/foto').status_code == 401
    with cli.session_transaction() as sesion:
        sesion['form_verificar_dataper'] = True
    assert cli.get('/form-pruebas/').location.endswith('/form-pruebas/asistencia')
    with cli.session_transaction() as sesion:
        sesion['form_documento'] = '47770006'
        sesion['form_personal_id'] = ids['Supervisora Seis']
        sesion['form_verificar_dataper'] = True
    assert cli.get('/form-pruebas/').location.endswith('/form-pruebas/dataper')
    assert cli.post('/form-pruebas/dataper', headers=csrf_header,
                    data={**datos, 'CARGO': 'SUPERVISOR', 'foto': _foto()}).status_code == 302
    inicio = cli.get('/form-pruebas/')
    assert inicio.status_code == 200 and b'foto-perfil-mobile' in inicio.data
    assert b'asistencia-action' not in inicio.data


def test_datos_y_juniors_del_mismo_proyecto(cuadrilla):
    cli, h, ids = cuadrilla
    assert cli.get('/form-pruebas/').location.endswith('/form-pruebas/asistencia')
    assert cli.get('/form-pruebas/caja-chica').location.endswith('/form-pruebas/asistencia')
    assert cli.get('/form-pruebas/asistencia').status_code == 200
    j = cli.get('/form-pruebas/asistencia/datos').json
    assert j['personal']['nombre'] == 'Principal Uno' and j['personal']['cargo'] == 'TECNICO ESPECIALISTA' and j['personal']['celular'] == '999111222'
    # Junior primero; sin otro proyecto, cesados, cargos de oficina (supervisor) ni él mismo.
    assert [x['nombre'] for x in j['juniors']] == ['Junior Dos', 'Otro Tres']
    assert j['hoy'] is None
    assert cli.get('/form-pruebas/asistencia/estado').json['marcado'] is False


def test_registra_una_vez_con_foto_y_coordenadas(cuadrilla):
    cli, h, ids = cuadrilla
    base = {'junior': str(ids['Junior Dos']), 'placa': 'abc-123', 'latitud': '-12.0464', 'longitud': '-77.0428', 'precision': '12'}
    r = cli.post('/form-pruebas/asistencia', headers=h, data={**base, 'latitud': ''}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'ubicación' in r.json['error']
    r = cli.post('/form-pruebas/asistencia', headers=h, data={**base, 'junior': str(ids['Entel Cuatro']), 'foto': _foto()}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'compañero' in r.json['error']
    r = cli.post('/form-pruebas/asistencia', headers=h, data={**base, 'placa': '', 'foto': _foto()}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'placa' in r.json['error']
    r = cli.post('/form-pruebas/asistencia', headers=h, data={**base, 'foto': _foto()}, content_type='multipart/form-data')
    assert r.status_code == 200, r.json
    reg = r.json['registro']
    assert reg['placa'] == 'ABC-123' and reg['junior'] == 'Junior Dos' and reg['latitud'] == -12.0464 and reg['precision'] == 12
    foto = cli.get('/form-pruebas/asistencia/foto/%d' % reg['id'])
    assert foto.status_code == 200 and foto.mimetype == 'image/jpeg'
    assert cli.get('/form-pruebas/asistencia/estado').json['marcado'] is True
    assert cli.get('/form-pruebas/').status_code == 200
    assert cli.get('/form-pruebas/asistencia/datos').json['hoy']['id'] == reg['id']
    r = cli.post('/form-pruebas/asistencia', headers=h, data={**base, 'foto': _foto()}, content_type='multipart/form-data')
    assert r.status_code == 400 and 'Ya registraste' in r.json['error']
    assert cli.post('/form-pruebas/asistencia', headers={'X-Ubicacion': h['X-Ubicacion']}, data={**base, 'foto': _foto()}, content_type='multipart/form-data').status_code == 403


def test_caminante_solo_sin_placa_ni_companero(app, cuadrilla):
    cli, h, ids = cuadrilla
    datos = {'movilidad': 'a_pie', 'companero': 'solo', 'latitud': '-12.05', 'longitud': '-77.04', 'precision': '9', 'foto': _foto()}
    r = cli.post('/form-pruebas/asistencia', headers=h, data=datos, content_type='multipart/form-data')
    assert r.status_code == 200, r.json
    reg = r.json['registro']
    assert reg['a_pie'] and reg['solo'] and reg['placa'] == '' and reg['junior'] == ''


def test_asistencia_es_individual(app, cuadrilla):
    from datetime import datetime
    from services.utilidades import ahora_peru
    cli, h, ids = cuadrilla
    hoy = ahora_peru().date()
    with app.app_context():
        # Otro técnico ya marcó hoy y puso a Principal Uno como compañero: eso no le marca asistencia.
        db.session.add(AsistenciaCuadrilla(fecha=hoy, personal_id=ids['Otro Tres'], documento='47770003', nombre='Otro Tres',
                                           proyecto='FLM - CLARO', junior_id=ids['Principal Uno'], junior_documento=DOC,
                                           junior_nombre='Principal Uno', placa='XYZ999', foto='2026-11/' + 'b' * 32 + '.jpg',
                                           latitud=-12.0, longitud=-77.0, registrado_en=datetime.now()))
        db.session.commit()
    try:
        assert cli.get('/form-pruebas/asistencia/estado').json['marcado'] is False
        datos = {'movilidad': 'vehiculo', 'placa': 'XYZ-999', 'companero': 'con', 'junior': str(ids['Otro Tres']),
                 'latitud': '-12.0', 'longitud': '-77.0', 'foto': _foto()}
        r = cli.post('/form-pruebas/asistencia', headers=h, data=datos, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
    finally:
        with app.app_context():
            AsistenciaCuadrilla.query.filter_by(documento='47770003').delete(); db.session.commit()


def test_sin_ubicacion_no_deja_actuar_y_cada_accion_guarda_su_punto(app, cuadrilla):
    cli, h, ids = cuadrilla
    sin = {k: v for k, v in h.items() if k != 'X-Ubicacion'}
    r = cli.post('/form-pruebas/ubicacion', headers=sin, json={'evento': 'Abrió Nucleus'})
    assert r.status_code == 428 and r.json['codigo'] == 'UBICACION'
    r = cli.post('/form-pruebas/caja-chica/solicitar', headers=sin, json={})
    assert r.status_code == 428
    assert cli.post('/form-pruebas/ubicacion', headers=h, json={'evento': 'Abrió Nucleus'}).status_code == 200
    with app.app_context():
        puntos = UbicacionMovil.query.filter_by(documento=DOC).all()
        assert [(p.evento, p.latitud, p.dispositivo) for p in puntos] == [('Abrió Nucleus', -12.0464, 'cel-1')]


@pytest.fixture
def gestor(app, client, monkeypatch):
    monkeypatch.setitem(app.config, 'ESPACIOS_HABILITADOS', True)
    with app.app_context():
        pids = {p.nombre: p.id for p in Proyecto.query.all()}
        u = Usuario(username='gestor-movil', nombre='Gestor Mobile', rol='gestor', password_hash='sin-login')
        db.session.add(u); db.session.flush(); uid = u.id
        for n in ('FLM - CLARO', 'Dataper'):
            db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=pids[n], restricciones='{}'))
        db.session.commit()
    with client.session_transaction() as s:
        s.update(user_id=uid, username='gestor-movil', rol='gestor')
    assert client.get('/personal/asistencia').status_code == 200
    with client.session_transaction() as s:
        token = s['asistencia_csrf']
    yield client, {'X-Asistencia-CSRF': token}, pids['FLM - CLARO']
    with app.app_context():
        AccesoProyecto.query.filter_by(usuario_id=uid).delete(); Usuario.query.filter_by(id=uid).delete(); db.session.commit()


def test_planilla_marca_mobile_falta_automatica_y_validacion(app, cuadrilla, gestor):
    from datetime import date, datetime
    tecnico, _, ids = cuadrilla
    c, h, claro = gestor
    principal, junior = ids['Principal Uno'], ids['Junior Dos']
    with app.app_context():
        r = AsistenciaCuadrilla(fecha=date(2026, 10, 5), personal_id=principal, documento=DOC, nombre='Principal Uno', proyecto='FLM - CLARO',
                                junior_id=junior, junior_documento='47770002', junior_nombre='Junior Dos', placa='ABC123',
                                foto='2026-10/' + 'a' * 32 + '.jpg', latitud=-12.0464, longitud=-77.0428, precision_m=10,
                                registrado_en=datetime(2026, 10, 5, 7, 40), dispositivo='cel-1')
        db.session.add(r)
        db.session.add_all([UbicacionMovil(documento=DOC, fecha=date(2026, 10, 5), hora=datetime(2026, 10, 5, 7, 40), latitud=-12.0464,
                                           longitud=-77.0428, precision_m=10, evento='Asistencia'),
                            UbicacionMovil(documento=DOC, fecha=date(2026, 10, 5), hora=datetime(2026, 10, 5, 8, 0), latitud=-11.65,
                                           longitud=-77.0428, precision_m=10, evento='Solicitud')])
        db.session.commit(); rid = r.id
    try:
        plan = {p['personal_id']: p['marcas'] for p in c.get('/api/asistencia/planilla?mes=2026-10&proyecto=%d' % claro).json['registros']}
        assert plan[principal]['5']['movil']['validacion'] == 'PENDIENTE' and plan[principal]['5']['movil']['companero'] == 'Junior Dos'
        # El compañero no marcó: falta, con el aviso de quién lo puso como compañero.
        assert plan[junior]['5']['estado'] == 'FALTA' and 'Principal Uno lo puso como compañero' in plan[junior]['5']['observacion']
        assert plan[principal]['6']['estado'] == 'FALTA' and plan[principal]['6']['auto'] is True  # martes sin marcar
        assert '11' not in plan[principal]  # domingo
        assert '4' not in plan[principal]  # antes de su primera marca
        assert not any(plan[ids['Otro Tres']].values())  # no usa Mobile: sin falta automática
        d = c.get('/api/asistencia/movil/%d' % rid).json
        assert d['editar'] and [p['evento'] for p in d['recorrido']] == ['Asistencia', 'Solicitud']
        assert any('20 min' in a and 'No cuadra' in a for a in d['alertas'])
        assert any('Junior Dos no marcó' in a for a in d['alertas']) and d['companero_hora'] == ''
        assert c.post('/api/asistencia/movil/%d' % rid, headers=h, json={'accion': 'observar'}).status_code == 400
        assert c.post('/api/asistencia/movil/%d' % rid, headers=h, json={'accion': 'validar'}).json['validacion'] == 'VALIDADA'
        with app.app_context():
            # Validar solo afecta a quien marcó, no a su compañero.
            assert {(a.personal_id, a.estado) for a in AsistenciaDiaria.query.filter_by(fecha=date(2026, 10, 5))} == {(principal, 'PRESENTE')}
        r = c.post('/api/asistencia/movil/%d' % rid, headers=h, json={'accion': 'rechazar', 'motivo': 'Marcó desde su casa'})
        assert r.status_code == 200 and r.json['validacion'] == 'RECHAZADA'
        assert tecnico.get('/form-pruebas/asistencia/estado').json['rechazo']['motivo'] == 'Marcó desde su casa'
        with app.app_context():
            assert {a.estado for a in AsistenciaDiaria.query.filter_by(fecha=date(2026, 10, 5))} == {'FALTA'}
    finally:
        with app.app_context():
            filas = [a.id for a in AsistenciaDiaria.query.filter(AsistenciaDiaria.personal_id.in_(ids.values()))]
            AsistenciaCambio.query.filter(AsistenciaCambio.asistencia_id.in_(filas)).delete(synchronize_session=False)
            AsistenciaDiaria.query.filter(AsistenciaDiaria.id.in_(filas)).delete(synchronize_session=False)
            db.session.commit()
