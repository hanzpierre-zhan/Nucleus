import json

from db import db
from models import NucleusData, Proyecto


def _cot(app, estado, extra=None):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        datos = {'N° COTIZACION': 'QA-EDIT-' + estado[:3], 'ESTADO COTIZACION': estado, 'GENERADA': '1', 'MOTIVO': 'antes',
                 'ITEMS_JSON': '[]', **(extra or {})}
        fila = NucleusData(proyecto_id=pid, key_value=datos['N° COTIZACION'], data_json=json.dumps(datos))
        db.session.add(fila); db.session.commit()
        return pid, fila.id, fila.key_value


def test_editar_en_cliente_antes_de_aprobar(app, auth_client):
    pid, rid, key = _cot(app, 'En Aprobación')
    try:
        r = auth_client.post('/api/cot-new/guardar', json={'key': key, 'data': {'MOTIVO': 'después'}})
        assert r.status_code == 200, r.get_data(as_text=True)
        with app.app_context():
            assert json.loads(db.session.get(NucleusData, rid).data_json)['MOTIVO'] == 'después'
    finally:
        with app.app_context():
            db.session.delete(db.session.get(NucleusData, rid)); db.session.commit()


def test_admin_edita_cualquier_campo_con_historial(app, auth_client, cambiar_rol):
    from models import HistorialCambios, NucleusHistory
    pid, rid, key = _cot(app, 'Aprobado', {'FECHA': '2026-11-19', '_SUSTENTO_FICHAS': {'x': {}}})
    try:
        campos = auth_client.get('/api/cot-new/admin-campos?key=' + key).get_json()['campos']
        nombres = {c['campo'] for c in campos}
        assert 'FECHA' in nombres and 'N° COTIZACION' not in nombres and '_SUSTENTO_FICHAS' not in nombres
        r = auth_client.post('/api/cot-new/admin-editar', json={'key': key, 'cambios': {'FECHA': '2026-11-18 10:30'}})
        assert r.status_code == 200 and r.get_json()['cambiados'] == 1
        assert auth_client.post('/api/cot-new/admin-editar', json={'key': key, 'cambios': {'N° COTIZACION': 'X'}}).status_code == 400
        with app.app_context():
            d = json.loads(db.session.get(NucleusData, rid).data_json)
            assert d['FECHA'] == '2026-11-18 10:30' and d['_SUSTENTO_FICHAS'] == {'x': {}}
            assert HistorialCambios.query.filter_by(key_value=key, campo_modificado='FECHA').count() == 1
            assert NucleusHistory.query.filter_by(key_value=key).count() >= 1
        cambiar_rol(auth_client, 'supervisor')
        assert auth_client.get('/api/cot-new/admin-campos?key=' + key).status_code == 403
    finally:
        with app.app_context():
            db.session.delete(db.session.get(NucleusData, rid)); db.session.commit()
