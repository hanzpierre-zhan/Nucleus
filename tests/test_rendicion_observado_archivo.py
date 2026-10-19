import json
import io
import pytest
from db import db
from models import Proyecto, NucleusData


@pytest.fixture
def solicitud_flujo(app, auth_client, monkeypatch):
    import blueprints.rendicion as flujo
    monkeypatch.setattr(flujo, '_avisar_flujo', lambda *args: None)
    monkeypatch.setattr(flujo, '_persistir_fotos_form', lambda *args: None)
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Rendicion').one()
        fila = NucleusData(proyecto_id=proyecto.id, key_value='REND-NUEVO-FLUJO',
                           data_json=json.dumps({'ESTADO': 'CON SUSTENTO', 'CODIGO DEPOSITO': 'COB-00123',
                           'MONTO PAGO': '350.00', 'FOTO PAGO': '/comprobante.jpg',
                           'FOTOS SUSTENTO': '["/foto.jpg"]', 'ADJUNTO CORREO VALIDACION': '/correo.msg'}))
        db.session.add(fila); db.session.commit()
        pid, rid = proyecto.id, fila.id
    auth_client.get(f'/switch_project/{pid}')
    yield rid
    with app.app_context():
        db.session.delete(db.session.get(NucleusData, rid)); db.session.commit()


def accion(client, nombre, **extra):
    return client.post('/api/rendicion/accion', json={'key': 'REND-NUEVO-FLUJO', 'accion': nombre, **extra})


def test_observacion_atencion_archivo_conservan_sustentos(auth_client, solicitud_flujo):
    assert accion(auth_client, 'observar').status_code == 400
    respuesta = accion(auth_client, 'observar', observaciones='Corregir el comprobante')
    assert respuesta.status_code == 200 and respuesta.json['estado'] == 'OBSERVADO'
    assert accion(auth_client, 'archivar').status_code == 409
    assert accion(auth_client, 'observar', observaciones='Aún pendiente').json['estado'] == 'OBSERVADO'
    assert accion(auth_client, 'sustentar', comentario='Corrección verificada').json['estado'] == 'SUSTENTADO'
    anterior = accion(auth_client, 'archivar')
    assert anterior.status_code == 200 and anterior.json['estado'] == 'ARCHIVADO'
    assert accion(auth_client, 'archivar').status_code == 409
    assert accion(auth_client, 'sustentar').status_code == 409
    assert accion(auth_client, 'observar', observaciones='Cambio').status_code == 409
    assert accion(auth_client, 'revertir').status_code == 400
    restaurada = accion(auth_client, 'desarchivar')
    assert restaurada.status_code == 200 and restaurada.json['estado'] == 'SUSTENTADO'
    for field in ('CODIGO DEPOSITO', 'MONTO PAGO', 'FOTO PAGO', 'FOTOS SUSTENTO',
                  'ADJUNTO CORREO VALIDACION', 'FECHA SUSTENTO', 'SUSTENTADO POR', 'COMENTARIOS SUSTENTO'):
        assert anterior.json['newData'][field] == restaurada.json['newData'][field]
    assert [evento['accion'] for evento in restaurada.json['newData']['_HISTORIAL_FLUJO']] == [
        'observar', 'observar', 'sustentar', 'archivar', 'desarchivar']
    assert accion(auth_client, 'desarchivar').status_code == 409


def test_atencion_directa_y_permisos(app, auth_client, solicitud_flujo):
    assert accion(auth_client, 'sustentar', comentario='Conforme').json['estado'] == 'SUSTENTADO'
    with auth_client.session_transaction() as session:
        session['rol'] = 'contrata'
        session['user_id'] = -999
        session['current_proyecto_id'] = None
        session['current_proyecto_nombre'] = ''
    assert accion(auth_client, 'archivar').status_code == 401  # La cuenta -999 no existe.


def cambiar_estado(app, rid, estado, **datos):
    with app.app_context():
        fila = db.session.get(NucleusData, rid)
        row = json.loads(fila.data_json); row.update(datos); row['ESTADO'] = estado
        fila.data_json = json.dumps(row); db.session.commit()


def test_rechazo_de_depositos_vuelve_validacion_y_puede_validar(app, auth_client, solicitud_flujo):
    from blueprints.rendicion import _etapa_de
    cambiar_estado(app, solicitud_flujo, 'VALIDADO', **{'Tipo de presupuesto': 'No refacturable'})
    assert accion(auth_client, 'rechazar').status_code == 400
    respuesta = accion(auth_client, 'rechazar', observaciones='Corregir la cuenta')
    assert respuesta.status_code == 200 and respuesta.json['estado'] == 'RECHAZADO'
    assert _etapa_de(respuesta.json['newData']) == 'VALIDACION'
    assert accion(auth_client, 'depositar').status_code == 409
    assert accion(auth_client, 'validar', tiempo='No aplica').json['estado'] == 'VALIDADO'


@pytest.mark.parametrize('origen', ['CON SUSTENTO', 'OBSERVADO'])
def test_rechazo_sustento_vuelve_evidencia(app, auth_client, solicitud_flujo, origen):
    from blueprints.rendicion import _etapa_de
    cambiar_estado(app, solicitud_flujo, origen)
    respuesta = accion(auth_client, 'rechazar', observaciones='Comprobante incorrecto')
    assert respuesta.status_code == 200 and respuesta.json['estado'] == 'RECHAZADO'
    assert _etapa_de(respuesta.json['newData']) == 'EVIDENCIA'
    assert respuesta.json['newData']['CODIGO DEPOSITO'] == 'COB-00123'
    assert accion(auth_client, 'validar', tiempo='No aplica').status_code == 409
    assert accion(auth_client, 'sustentar').status_code == 409
    assert accion(auth_client, 'observar', observaciones='Cambio').status_code == 409


@pytest.mark.parametrize('origen', ['PENDIENTE', 'DEPOSITADO'])
def test_anular_validacion_evidencia_sin_perder_datos(app, auth_client, solicitud_flujo, origen):
    cambiar_estado(app, solicitud_flujo, origen)
    assert accion(auth_client, 'anular').status_code == 400
    respuesta = accion(auth_client, 'anular', observaciones='Solicitud anulada por revisión')
    assert respuesta.status_code == 200 and respuesta.json['estado'] == 'ANULADO'
    assert respuesta.json['newData']['FOTO PAGO'] == '/comprobante.jpg'
    for nombre in ('validar', 'rechazar', 'depositar', 'sustentar', 'observar', 'archivar', 'desarchivar', 'revertir', 'devolver'):
        assert accion(auth_client, nombre, tiempo='No aplica', observaciones='Prueba').status_code == 409


def test_evidencia_solo_anula_y_legacy_sigue_visible(app, auth_client, solicitud_flujo):
    from blueprints.rendicion import _etapa_de
    cambiar_estado(app, solicitud_flujo, 'DEPOSITADO')
    assert accion(auth_client, 'rechazar', observaciones='Prueba').status_code == 409
    assert accion(auth_client, 'sustentar').status_code == 409
    assert _etapa_de({'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'PENDIENTE'}) == 'ANULADO'
    assert _etapa_de({'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'VALIDADO'}) == 'VALIDACION'
    assert _etapa_de({'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'CON SUSTENTO'}) == 'EVIDENCIA'


def test_vistas_nuevas_sin_cambiar_estado_historico(auth_client, solicitud_flujo):
    pagina = auth_client.get('/').get_data(as_text=True)
    for vista in ('observado', 'archivado', 'cerrado', 'rechazados'):
        assert f'data-vista="{vista}"' in pagina
    assert '> Archivar <' in pagina and '> Anulado <' in pagina and '> Atendido <' in pagina


@pytest.mark.parametrize('estado,actualizados', [('OBSERVADO', 1), ('ARCHIVADO', 0), ('ANULADO', 0), ('RECHAZADO', 1)])
def test_sync_no_saca_observado_ni_archivado(app, auth_client, solicitud_flujo, monkeypatch, estado, actualizados):
    from models import AppConfig
    import blueprints.admin as admin
    with app.app_context():
        fila = db.session.get(NucleusData, solicitud_flujo)
        datos = json.loads(fila.data_json); datos['ESTADO'] = estado
        if estado == 'RECHAZADO': datos['_RECHAZO_ETAPA'] = 'EVIDENCIA'
        fila.data_json = json.dumps(datos)
        pid = fila.proyecto_id
        config = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        previo = config.valor if config else None
        db.session.commit()
    monkeypatch.setattr(admin.urllib.request, 'urlopen', lambda *args, **kwargs:
                        io.BytesIO(b'CODIGO DEPOSITO,Marca temporal,Comentario\nCOB-00123,2026-10-13 10:00:00,Corregido\n'))
    try:
        respuesta = auth_client.post('/api/rendicion/sync_sustentos')
        assert respuesta.status_code == 200
        assert respuesta.json['actualizados'] == actualizados
        with app.app_context():
            final = json.loads(db.session.get(NucleusData, solicitud_flujo).data_json)
            assert final['ESTADO'] == ('CON SUSTENTO' if estado == 'RECHAZADO' else estado)
            assert final['FOTO PAGO'] == '/comprobante.jpg'
            assert ('SUSTENTO_COMENTARIO' in final) == bool(actualizados)
    finally:
        with app.app_context():
            config = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
            if config:
                if previo is None: db.session.delete(config)
                else: config.valor = previo
                db.session.commit()
