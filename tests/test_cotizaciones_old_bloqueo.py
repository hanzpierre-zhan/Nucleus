"""Switch de Cotizaciones old: solo lectura para el módulo anterior; la vista nueva sigue trabajando."""
from models import Proyecto


def _activar(cliente, bloquear):
    r = cliente.post('/api/cotizacion/modulo-old', json={'bloquear': bloquear})
    assert r.status_code == 200 and r.json['bloqueado'] is bloquear


def test_switch_bloquea_old_pero_no_la_vista_nueva(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
    auth_client.get('/switch_project/%d?next=/' % pid)
    _activar(auth_client, True)
    try:
        # Desde el módulo old: acciones y edición de filas quedan bloqueadas.
        r = auth_client.post('/api/cotizacion/accion', json={'key': 'X', 'accion': 'enviar'})
        assert r.status_code == 423 and 'solo lectura' in r.json['error']
        assert auth_client.post('/api/rows/add', json={}).status_code == 423
        # La misma llamada desde Cotizaciones (Cot_New) pasa el bloqueo (responde su propia validación).
        r = auth_client.post('/api/cotizacion/accion', json={'key': 'X', 'accion': 'enviar'}, headers={'X-Nucleus-Vista': 'cot-new'})
        assert r.status_code != 423
        pagina = auth_client.get('/')
        assert 'Módulo desactivado'.encode() in pagina.data and 'solo lectura'.encode() in pagina.data
        menu = auth_client.get('/cot-new/').data.decode()
        assert 'Cotizaciones old' in menu and '>Backup<' in menu and 'Cot_New' not in menu
    finally:
        _activar(auth_client, False)
    r = auth_client.post('/api/cotizacion/accion', json={'key': 'X', 'accion': 'enviar'})
    assert r.status_code != 423
