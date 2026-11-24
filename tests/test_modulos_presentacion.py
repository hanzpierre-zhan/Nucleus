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


def test_combustible_y_generadores_en_backup(app, auth_client, client):
    """Combustible y Generadores pasaron a backup: sus datos siguen en la base, pero nadie los ve ni entra."""
    from db import db
    from models import AccesoProyecto, Usuario
    with app.app_context():
        comb = Proyecto.query.filter_by(nombre='Combustible').one().id
        gen = Proyecto.query.filter_by(nombre='Generadores').one().id
        flm = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        usuario = Usuario(username='gestor-comb-gen', password_hash='prueba', rol='gestor')
        db.session.add(usuario)
        db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=usuario.id, proyecto_id=flm, restricciones='{}'))
        db.session.commit()
        uid = usuario.id
    try:
        # Ni el administrador general puede entrar.
        assert auth_client.get('/vista/combustible/').status_code == 403
        for pid in (comb, gen):
            auth_client.get('/switch_project/%d' % pid)
            with auth_client.session_transaction() as ses:
                assert ses.get('current_proyecto_id') != pid
        with client.session_transaction() as ses:
            ses.update({'user_id': uid, 'username': 'gestor-comb-gen', 'rol': 'gestor',
                        'current_proyecto_id': flm, 'current_proyecto_nombre': 'FLM - CLARO'})
        pagina = client.get('/')
        assert b'<span class="sidebar-link-text">Generadores</span>' not in pagina.data
        assert b'<span class="sidebar-link-text">Combustible</span>' not in pagina.data
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete()
            Usuario.query.filter_by(id=uid).delete()
            db.session.commit()
