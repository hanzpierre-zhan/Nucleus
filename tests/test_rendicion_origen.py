import io
import json
from db import db
from models import AppConfig, Proyecto, NucleusData
from services.rendicion_origen import recibir_en_nucleus


def test_sync_recibe_entel_pext_y_los_demas_sin_duplicar(app, auth_client, monkeypatch):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Rendicion').one().id
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='rendicion_csv_url').first()
        old = cfg.valor if cfg else None
        if cfg is None:
            cfg = AppConfig(proyecto_id=pid, clave='rendicion_csv_url')
            db.session.add(cfg)
        cfg.valor = 'https://example.test/rendicion.csv'
        db.session.commit()
    csv = ('Marca temporal,Nombre del proyecto\n'
           'ORIGEN-PEXT,Entel - Pext\n'
           'ORIGEN-ENTEL,Entel\n'
           'ORIGEN-CLARO,Claro\n'
           'ORIGEN-INTEGRATEL,Integratel\n')
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: io.BytesIO(csv.encode()))
    response = auth_client.post('/api/rendicion/sync')
    assert response.status_code == 200, response.json
    assert response.json['nuevas'] == 4
    repetida = auth_client.post('/api/rendicion/sync')
    assert repetida.status_code == 200, repetida.json
    assert repetida.json['nuevas'] == 0
    with app.app_context():
        rows = NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.key_value.like('ORIGEN-%')).all()
        assert len(rows) == 4
        assert {json.loads(row.data_json)['Nombre del proyecto'] for row in rows} == {'Entel - Pext', 'Entel', 'Claro', 'Integratel'}
        for row in rows:
            db.session.delete(row)
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='rendicion_csv_url').one()
        if old is None:
            db.session.delete(cfg)
        else:
            cfg.valor = old
        db.session.commit()


def test_recepcion_admite_entel_pext_con_espacios_y_mayusculas():
    assert recibir_en_nucleus({'Nombre del proyecto': '  ENTEL - PEXT  '})
    assert recibir_en_nucleus({'Nombre del proyecto': 'Entel'})
