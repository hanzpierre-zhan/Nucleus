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
