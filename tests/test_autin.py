"""Contratos HTTP de la pestaña AUTIN.

AUTIN vivía dentro de `blueprints/wo.py` sin pruebas propias. Estos tests fijan
su comportamiento público (rutas `/api/autin/*`) para que la extracción a
`blueprints/autin.py` no pase desapercibida si algo se rompe.
"""


def test_config_get_devuelve_estado(auth_client):
    r = auth_client.get('/api/autin/config')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert {'raiz', 'origen', 'base_url', 'sp_link', 'sp_activo', 'existe', 'editable'} <= set(data)


def test_fotos_agrupa_por_estado_sin_carpeta(auth_client):
    r = auth_client.get('/api/autin/fotos?wo=CM-INEXISTENTE-000')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['wo'] == 'CM-INEXISTENTE-000'
    assert set(data['grupos']) == {'llegada', 'completado', 'salida', 'suspendido', 'otros'}
    assert data['total'] == 0


def test_fotos_sin_wo_es_400(auth_client):
    r = auth_client.get('/api/autin/fotos')
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_zip_sin_wo_es_400(auth_client):
    r = auth_client.get('/api/autin/zip')
    assert r.status_code == 400


def test_requiere_sesion(client):
    assert client.get('/api/autin/config').status_code == 401
