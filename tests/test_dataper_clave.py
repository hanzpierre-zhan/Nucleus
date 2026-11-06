"""Un administrativo con Dataper restablece la clave del portal de un técnico."""
import json
from db import db
from models import ClaveTecnico, HistorialCambios, NucleusData, Proyecto


def test_restablecer_clave_desde_dataper(app, auth_client):
    from services import claves_tecnico
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value='77778888',
                                   data_json=json.dumps({'DOCUMENTO': '77778888', 'TECNICO': 'Técnico Clave', 'ESTADO': 'ACTIVO'})))
        db.session.commit()
        claves_tecnico.cambiar('77778888', 'Propia-2026')
    try:
        auth_client.get('/switch_project/%s' % pid)
        pagina = auth_client.get('/').get_data(as_text=True)
        assert "_clave_portal" in pagina and '/api/dataper/clave/restablecer' in pagina
        assert auth_client.post('/api/dataper/clave/restablecer', json={'key': 'NO-EXISTE'}).status_code == 404
        r = auth_client.post('/api/dataper/clave/restablecer', json={'key': '77778888'})
        assert r.status_code == 200, r.json
        with app.app_context():
            assert db.session.get(ClaveTecnico, '77778888') is None  # vuelve al documento
            assert claves_tecnico.verificar('77778888', '77778888') and claves_tecnico.debe_cambiar('77778888')
            assert HistorialCambios.query.filter_by(key_value='77778888', campo_modificado='CLAVE PORTAL').count() == 1
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid, key_value='77778888').delete()
            HistorialCambios.query.filter_by(key_value='77778888').delete()
            ClaveTecnico.query.filter_by(documento='77778888').delete()
            db.session.commit()


def test_menu_dice_dataper(auth_client):
    pagina = auth_client.get('/').get_data(as_text=True)
    assert 'sidebar-link-text">Dataper</span>' in pagina and 'sidebar-link-text">Personal</span>' not in pagina
