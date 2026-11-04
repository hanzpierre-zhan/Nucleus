import json
from db import db
from models import NucleusData, NucleusHistory
from test_sustento_por_wo import caso


def test_error_de_lectura_no_presenta_ficha_vacia(app, auth_client, caso, monkeypatch):
    import blueprints.cotizacion as cot
    auth_client.get('/switch_project/%s' % caso['cot'])
    with app.app_context():
        original = db.session.get(NucleusData, caso['ids'][2]).data_json
    def fallo(*args):
        raise ValueError('Lectura fallida')
    monkeypatch.setattr(cot, 'efectivos', fallo)
    r = auth_client.get('/api/cotizacion/sustento?key=COT-SUST-TEST')
    assert r.status_code == 503
    assert 'wos' not in r.json
    with app.app_context():
        assert db.session.get(NucleusData, caso['ids'][2]).data_json == original


def test_formulario_vacio_no_borra_y_edicion_desactualizada_no_pisa(app, auth_client, caso):
    auth_client.get('/switch_project/%s' % caso['cot'])
    with app.app_context():
        row = db.session.get(NucleusData, caso['ids'][0])
        d = json.loads(row.data_json)
        d.update({'INICIO EJECUCION': '2026-10-20 08:00:00', '_EVIDENCIA_INICIO': '["/foto-existente.jpg"]'})
        row.data_json = json.dumps(d); db.session.commit()
        original = row.data_json
    for cambios, base in [
        ({'_BITACORA_INICIO': '', 'INICIO EJECUCION': '', '_EVIDENCIA_INICIO': '[]'}, None),
        ({'_BITACORA_INICIO': 'Pantalla antigua'}, {'_BITACORA_INICIO': 'Versión antigua'}),
    ]:
        payload = {'key': 'COT-SUST-TEST', 'wo': 'WO-SUST-1', 'evidencia': cambios}
        if base is not None: payload['base_evidencia'] = base
        result = auth_client.post('/api/cotizacion/sustento/wo', json=payload)
        assert result.status_code == 409, result.json
        with app.app_context():
            assert db.session.get(NucleusData, caso['ids'][0]).data_json == original
    result = auth_client.post('/api/cotizacion/sustento/wo', json={
        'key': 'COT-SUST-TEST', 'wo': 'WO-SUST-1',
        'evidencia': {'_BITACORA_CIERRE': 'Detalle nuevo'}, 'base_evidencia': {'_BITACORA_CIERRE': ''}})
    assert result.status_code == 200, result.json
    assert result.json['wo_data']['_BITACORA_INICIO'] == 'Comentario WO 1'
    assert result.json['wo_data']['INICIO EJECUCION'] == '2026-10-20 08:00:00'
    with app.app_context():
        history = NucleusHistory.query.filter_by(proyecto_id=caso['flm'], key_value='WO-SUST-1').all()
        assert any(h.data_json == original for h in history)


def test_correccion_explicita_con_base_y_ficha_sin_wo_con_respaldo(app, auth_client, caso):
    with app.app_context():
        cot = db.session.get(NucleusData, caso['ids'][2]); d = json.loads(cot.data_json)
        d['NUMERO WO'] = ''; d['_BITACORA_INICIO'] = 'Antecedente original'
        d['_SUSTENTO_FICHAS'] = {'': {'location_picture': '/ubicacion-conservada.jpg',
            'item_photos': {'item-retirado': [{'url': '/antes.jpg', 'phase': 'before'}]}}}
        cot.data_json = json.dumps(d); db.session.commit(); original = cot.data_json
    auth_client.get('/switch_project/%s' % caso['cot'])
    result = auth_client.post('/api/cotizacion/sustento/wo', json={'key': 'COT-SUST-TEST',
        'wo': '', 'evidencia': {'_BITACORA_INICIO': ''},
        'base_evidencia': {'_BITACORA_INICIO': 'Antecedente original'}, 'manual': {'region': 'ICA'}})
    assert result.status_code == 200, result.json
    ficha = result.json['newData']['_SUSTENTO_FICHAS']['']
    assert ficha['location_picture'] == '/ubicacion-conservada.jpg'
    assert ficha['item_photos']['item-retirado'][0]['url'] == '/antes.jpg'
    with app.app_context():
        assert NucleusHistory.query.filter_by(proyecto_id=caso['cot'],key_value='COT-SUST-TEST',data_json=original).count() == 1
