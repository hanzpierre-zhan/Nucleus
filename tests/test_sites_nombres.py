import json

from db import db
from models import NucleusData, Proyecto


def _crear_site(nombre):
    """Crea (o reutiliza) el maestro SITE y devuelve (id, debe_borrarse)."""
    site = Proyecto.query.filter_by(nombre='SITE').first()
    if site is None:
        site = Proyecto(nombre='SITE')
        db.session.add(site)
        db.session.flush()
        return site.id, True
    return site.id, False


def test_api_sites_nombres_sugiere_solo_el_maestro_site(app, auth_client):
    """El autocompletado sale solo del maestro SITE (columna 'Nombre').

    Antes se mezclaban Cotizaciones y Rendición; ahora la fuente es única.
    """
    site_creado = None
    with app.app_context():
        cot = Proyecto.query.filter_by(nombre='Cotizaciones').first()
        assert cot is not None, 'El proyecto Cotizaciones debe existir (migraciones).'
        site_id, creado = _crear_site('SITE')
        site_creado = site_id if creado else None
        db.session.add(NucleusData(proyecto_id=cot.id, key_value='SITE-SUG-1',
                                   data_json=json.dumps({'NOMBRE SITE': 'Site Solo De Cotizacion'})))
        db.session.add(NucleusData(proyecto_id=site_id, key_value='SITE-SUG-2',
                                   data_json=json.dumps({'Nombre': 'Site Desde Maestro'})))
        db.session.commit()
    try:
        resp = auth_client.get('/api/sites/nombres')
        assert resp.status_code == 200
        nombres = resp.get_json()
        assert isinstance(nombres, list)
        assert 'Site Desde Maestro' in nombres
        assert 'Site Solo De Cotizacion' not in nombres
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


def test_catalogos_autocompletar_usa_la_columna_nombre(app, auth_client):
    """El autocompletado genérico reconoce la columna real del maestro SITE.

    Era el defecto de fondo: solo aceptaba claves tipo 'nombre site' y devolvía
    siempre una lista vacía, así que los campos de site de los demás módulos no
    sugerían nada.
    """
    site_creado = None
    with app.app_context():
        site_id, creado = _crear_site('SITE')
        site_creado = site_id if creado else None
        db.session.add(NucleusData(proyecto_id=site_id, key_value='SITE-SUG-3',
                                   data_json=json.dumps({'Nombre': 'Site Columna Nombre'})))
        db.session.commit()
    try:
        resp = auth_client.get('/api/catalogos/autocompletar')
        assert resp.status_code == 200
        datos = resp.get_json()
        assert 'Site Columna Nombre' in datos['sites']
        assert len(datos['departamentos']) == 25
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.key_value.like('SITE-SUG-%')).delete(synchronize_session=False)
            if site_creado is not None:
                creado = db.session.get(Proyecto, site_creado)
                if creado is not None:
                    db.session.delete(creado)
            db.session.commit()
