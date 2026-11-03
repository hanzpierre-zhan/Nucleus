"""El estado no se salta el flujo y las fotos no van a un disco que se borra."""
import json
from db import db
from models import NucleusData
from test_sustento_por_wo import caso, foto  # noqa: F401
from test_sustento_flujo_completo import _prep, _abrir


def _estado(app, caso):
    with app.app_context():
        return json.loads(db.session.get(NucleusData, caso['ids'][2]).data_json)['ESTADO COTIZACION']


def test_rol_no_admin_no_cambia_estado_a_mano(app):
    from flask import session
    from blueprints.rows import _error_estado_cotizacion
    fila = {'ESTADO COTIZACION': 'Aprobado'}
    with app.test_request_context():
        session.update(current_proyecto_nombre='Cotizaciones')
        for rol in ('supervisor', 'gestor', 'contrata'):
            session['rol'] = rol
            assert _error_estado_cotizacion(fila, {'ESTADO COTIZACION': 'Atendido'})
            # Reenviar el mismo estado (el editor lo hace) sigue permitido
            assert _error_estado_cotizacion(fila, {'ESTADO COTIZACION': 'Aprobado'}) is None
        for rol in ('zeno', 'suport'):
            session['rol'] = rol
            assert _error_estado_cotizacion(fila, {'ESTADO COTIZACION': 'Atendido'}) is None
        session.update(current_proyecto_nombre='FLM - CLARO', rol='gestor')
        assert _error_estado_cotizacion(fila, {'ESTADO COTIZACION': 'Atendido'}) is None


def test_admin_puede_corregir_estado(app, auth_client, caso):
    auth_client.get('/switch_project/%s' % caso['cot'])
    r = auth_client.post('/api/rows/update', json={'key': 'COT-SUST-TEST', 'field': 'ESTADO COTIZACION', 'value': 'Atendido'})
    assert r.status_code == 200, r.json
    assert _estado(app, caso) == 'Atendido'


def test_render_sin_b2_rechaza_fotos_del_sustento(app, auth_client, caso, monkeypatch):
    _prep(app, caso, 'WO-SUST-1'); auth_client.get('/switch_project/%s' % caso['cot'])
    item = _abrir(auth_client)['items'][0]['key']
    monkeypatch.setenv('RENDER', 'true')
    for k in ('B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY'):
        monkeypatch.setitem(app.config, k, '')
    r = auth_client.post('/api/cotizacion/sustento/item-foto', data={'key': 'COT-SUST-TEST', 'wo': 'WO-SUST-1', 'item_key': item,
                         'phase': 'before', 'foto': (foto(), 'f.png')}, content_type='multipart/form-data')
    assert r.status_code == 503 and 'almacenamiento' in r.json['error']
