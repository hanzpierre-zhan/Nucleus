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


def test_combustible_incluye_generadores(app, auth_client):
    """Generadores vive dentro de Combustible: se entra con un botón y se
    vuelve con otro; el menú lateral solo muestra Combustible."""
    with app.app_context():
        comb = Proyecto.query.filter_by(nombre='Combustible').one().id
        gen = Proyecto.query.filter_by(nombre='Generadores').one().id
    enlace_gen = ('href="/switch_project/%d?next=/"' % gen).encode()
    enlace_comb = ('href="/switch_project/%d?next=/"' % comb).encode()

    auth_client.get('/switch_project/%d' % comb)
    combustible = auth_client.get('/')
    assert combustible.status_code == 200
    assert b'Volver a Combustible' not in combustible.data
    # Una sola entrada a Generadores: el botón (ya no hay enlace en el menú).
    assert combustible.data.count(enlace_gen) == 1

    auth_client.get('/switch_project/%d' % gen)
    generadores = auth_client.get('/')
    assert generadores.status_code == 200
    assert b'Volver a Combustible' in generadores.data
    # El enlace del menú a Combustible más el botón de volver.
    assert generadores.data.count(enlace_comb) == 2
    # El menú marca Combustible mientras se está en Generadores.
    assert b'class="sidebar-link active"' in generadores.data


def test_gestor_sin_combustible_conserva_generadores(app, client):
    """Generadores vive dentro de Combustible, pero el Gestor (que no ve
    Combustible) conserva su entrada propia para no perder el acceso."""
    from db import db
    from models import AccesoProyecto, Proyecto, Usuario
    with app.app_context():
        flm = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        usuario = Usuario(username='gestor-comb-gen', password_hash='prueba', rol='gestor')
        db.session.add(usuario)
        db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=usuario.id, proyecto_id=flm, restricciones='{}'))
        db.session.commit()
        uid = usuario.id
    try:
        with client.session_transaction() as ses:
            ses.update({'user_id': uid, 'username': 'gestor-comb-gen', 'rol': 'gestor',
                        'current_proyecto_id': flm, 'current_proyecto_nombre': 'FLM - CLARO'})
        pagina = client.get('/')
        assert pagina.status_code == 200
        assert b'<span class="sidebar-link-text">Generadores</span>' in pagina.data
        assert b'<span class="sidebar-link-text">Combustible</span>' not in pagina.data
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete()
            Usuario.query.filter_by(id=uid).delete()
            db.session.commit()
