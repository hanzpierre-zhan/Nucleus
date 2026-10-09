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
