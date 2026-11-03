"""Un administrador devuelve a Sustentar una cotización con el sustento ya aprobado."""
import json
from db import db
from models import NucleusData
from test_sustento_por_wo import caso  # noqa: F401
from test_sustento_flujo_completo import _prep


def _accion(c, accion, **extra):
    return c.post('/api/cotizacion/accion', json={'key': 'COT-SUST-TEST', 'accion': accion, **extra})


def _aprobar(app, c, caso, wos):
    _prep(app, caso, wos); c.get('/switch_project/%s' % caso['cot'])
    wo = wos.split(',')[0].strip()
    assert c.post('/api/cotizacion/sustento/guardar', json={'key': 'COT-SUST-TEST', 'wo': wo,
                  'evidencia': {'_BITACORA_INICIO': 'Hecho'}}).status_code == 200
    r = _accion(c, 'aprobar_sustento'); assert r.status_code == 200, r.json
    assert _accion(c, 'revertir').status_code == 403  # aprobado: bloqueado
    return wo


def test_admin_reabre_sustento_aprobado_y_vuelve_a_editarse(app, auth_client, caso):
    for wos in ('WO-SUST-1', 'WO-NO-FLM'):
        wo = _aprobar(app, auth_client, caso, wos)
        r = _accion(auth_client, 'reabrir_sustento')
        assert r.status_code == 200, r.json
        assert r.json['pestania'] == 'sustentar'
        assert not r.json['newData'].get('_SUSTENTO_APROBADO')
        with app.app_context():
            wo_flm = json.loads(db.session.get(NucleusData, caso['ids'][0]).data_json)
            assert not wo_flm.get('_SUSTENTO_APROBADO_COT')
        # El sustento se puede editar y conserva lo que tenía
        r = auth_client.post('/api/cotizacion/sustento/wo', json={'key': 'COT-SUST-TEST', 'wo': wo,
                             'evidencia': {'_BITACORA_INICIO': 'Corregido'}})
        assert r.status_code == 200, r.json
        assert r.json['wo_data']['_BITACORA_INICIO'] == 'Corregido'


def test_solo_admin_y_solo_desde_atendido(app, auth_client, caso):
    from flask import session
    _prep(app, caso, 'WO-SUST-1'); auth_client.get('/switch_project/%s' % caso['cot'])
    r = _accion(auth_client, 'reabrir_sustento')  # está en Sustentar
    assert r.status_code == 409
    from blueprints.cotizacion import _reabrir_sustento
    with app.test_request_context():
        session['rol'] = 'gestor'
        assert _reabrir_sustento(None, None, {})[1] == 403
