import json
from db import db
from models import Proyecto, NucleusData


def test_api_sites_nombres_sugiere_sites_registrados(app, auth_client):
    site_creado = None
    with app.app_context():
        cot = Proyecto.query.filter_by(nombre='Cotizaciones').first()
        assert cot is not None, 'El proyecto Cotizaciones debe existir (migraciones).'
        site = Proyecto.query.filter_by(nombre='SITE').first()
        if site is None:
            site = Proyecto(nombre='SITE')
            db.session.add(site)
            db.session.flush()
            site_creado = site.id
        db.session.add(NucleusData(proyecto_id=cot.id, key_value='SITE-SUG-1',
                                   data_json=json.dumps({'NOMBRE SITE': 'Site Desde Cotizacion'})))
        db.session.add(NucleusData(proyecto_id=site.id, key_value='SITE-SUG-2',
                                   data_json=json.dumps({'Nombre': 'Site Desde Maestro'})))
        db.session.commit()
    try:
        resp = auth_client.get('/api/sites/nombres')
        assert resp.status_code == 200
        nombres = resp.get_json()
        assert isinstance(nombres, list)
        assert 'Site Desde Cotizacion' in nombres
        assert 'Site Desde Maestro' in nombres
        assert nombres == sorted(nombres)
        assert all(isinstance(n, str) for n in nombres)
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.key_value.like('SITE-SUG-%')).delete(synchronize_session=False)
            if site_creado is not None:
                creado = db.session.get(Proyecto, site_creado)
                if creado is not None:
                    db.session.delete(creado)
            db.session.commit()
