import json
import re

NOMBRES = ('Juan Carlos Espilco Canales', 'Victor Manuel Caro Ojeda', 'Gary William Arenas Bazan')


def test_componente_catalogo_integratel():
    from blueprints.cot_new import SUPERVISORES, SUPERVISORES_CLIENTE

    assert set(NOMBRES) <= set(SUPERVISORES_CLIENTE['INTEGRATEL'])
    assert not set(NOMBRES).intersection(SUPERVISORES)
    assert not set(NOMBRES).intersection(SUPERVISORES_CLIENTE['CLARO'])


def test_integracion_configuracion_editor(auth_client):
    respuesta = auth_client.get('/cot-new/')
    assert respuesta.status_code == 200
    contenido = re.search(rb'id="cn-config"[^>]*>(.*?)</script>', respuesta.data, re.S)
    assert set(NOMBRES) <= set(json.loads(contenido.group(1))['supervisores_cliente']['INTEGRATEL'])
