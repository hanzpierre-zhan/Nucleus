import pytest
from models import Proyecto


@pytest.mark.parametrize('nombre', [
    'Rendicion', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO',
    'Cotizaciones', 'Combustible', 'Dataper', 'Material', 'Generadores', 'SITE',
])
def test_modulos_cargan_con_ventanas_compartidas(app, auth_client, nombre):
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre=nombre).one()
        pid = proyecto.id
    auth_client.get('/switch_project/%d' % pid)
    respuesta = auth_client.get('/')
    assert respuesta.status_code == 200
    assert b'id="rend-val-form" class="rend-form-card"' in respuesta.data
    assert b'id="rend-dep-form" class="rend-form-card"' in respuesta.data
    assert b'<details id="rend-resumen"' in respuesta.data


def test_sites_y_mapa_son_un_solo_modulo(app, auth_client):
    """Sites y Mapa de Sites comparten módulo: el mapa se abre con un botón
    dentro de Sites y desde el mapa se vuelve con otro botón."""
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='SITE').one().id
    auth_client.get('/switch_project/%d' % pid)
    pagina = auth_client.get('/')
    assert pagina.status_code == 200
    assert b'Mapa de Site' in pagina.data
    # Una sola entrada al mapa: el botón del módulo (ya no hay enlace en el menú).
    assert pagina.data.count(b'href="/mapa-site"') == 1
    mapa = auth_client.get('/mapa-site')
    assert mapa.status_code == 200
    assert b'Volver a Sites' in mapa.data
    assert b'href="/"' in mapa.data
    # El menú marca Sites mientras se está en el mapa.
    assert b'class="sidebar-link active"' in mapa.data


def test_combustible_en_backup_y_generadores_en_abastecimiento(app, auth_client, client):
    from db import db
    from models import AccesoProyecto, Usuario
    with app.app_context():
        gen = Proyecto.query.filter_by(nombre='Generadores').one().id
        flm = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        usuario = Usuario(username='gestor-comb-gen', password_hash='prueba', rol='gestor')
        db.session.add(usuario)
        db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=usuario.id, proyecto_id=flm, restricciones='{}'))
        db.session.commit()
        uid = usuario.id
    try:
        pagina = auth_client.get('/vista/combustible/')
        assert pagina.status_code == 200
        assert pagina.data.count(b'<span class="sidebar-link-text">Combustible</span>') == 1
        backup = pagina.data.split(b'data-grupo="backup-config"', 1)[1]
        assert b'href="/vista/combustible/"' in backup
        assert b'<span class="sidebar-link-text">Generadores</span>' not in pagina.data
        destino = auth_client.get('/switch_project/%d?next=/' % gen)
        assert destino.location.endswith('/abastecimiento/?estado=generadores')
        assert auth_client.get(destino.location).status_code == 200
        with client.session_transaction() as ses:
            ses.update({'user_id': uid, 'username': 'gestor-comb-gen', 'rol': 'gestor',
                        'current_proyecto_id': flm, 'current_proyecto_nombre': 'FLM - CLARO'})
        pagina = client.get('/')
        assert b'<span class="sidebar-link-text">Generadores</span>' not in pagina.data
        assert b'<span class="sidebar-link-text">Combustible</span>' not in pagina.data
        assert client.get('/vista/combustible/').status_code == 403
        assert client.get('/abastecimiento/').status_code == 403
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete()
            Usuario.query.filter_by(id=uid).delete()
            db.session.commit()


def test_abastecimiento_aparece_en_modulos(auth_client):
    pagina = auth_client.get('/abastecimiento/')
    assert pagina.status_code == 200
    assert b'href="/abastecimiento/" class="sidebar-link active"' in pagina.data
    assert b'fa-mobile-screen-button' in pagina.data
    assert b'?estado=generadores' in pagina.data
    assert b'id="abastecimiento-titulo"' not in pagina.data
