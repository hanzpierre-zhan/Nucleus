import pytest


def test_orden_incluye_identidad_evidencia_flujo_y_kpi(auth_client):
    fields=['_evidencia_btn','KPI_PRUEBA','_key','_accion_cot','_accion']
    columns=[{'field':field,'visible':True} for field in fields]
    response=auth_client.post('/api/columns/layout',json={'columns':columns})
    assert response.status_code==200
    assert auth_client.get('/api/columns/layout').json==columns
    auth_client.post('/api/columns/layout',json={'columns':[]})


@pytest.mark.parametrize('rol', ['zeno', 'suport', 'admin', 'gestor', 'supervisor', 'contrata', 'demo'])
def test_solo_zeno_suport_modifican_vista(app, auth_client, cambiar_rol, rol):
    from db import db
    from models import AccesoProyecto
    with auth_client.session_transaction() as ses:
        uid, pid = ses['user_id'], ses['current_proyecto_id']
    with app.app_context():
        acceso = AccesoProyecto.query.filter_by(usuario_id=uid, proyecto_id=pid).first()
        creado = acceso is None
        if creado:
            db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=pid))
            db.session.commit()
    vista = 'prueba_permisos'
    original = [{'field': 'MOTIVO RECHAZO', 'visible': False}, {'field': 'ESTADO', 'visible': True}]
    assert auth_client.post('/api/columns/layout', json={'vista': vista, 'columns': original}).status_code == 200
    try:
        cambiar_rol(auth_client, rol)
        cambio = [{'field': 'ESTADO', 'visible': False}]
        respuesta = auth_client.post('/api/columns/layout', json={'vista': vista, 'columns': cambio})
        permitido = rol in ('zeno', 'suport')
        assert respuesta.status_code == (200 if permitido else 403), respuesta.get_data(as_text=True)
        assert auth_client.get('/api/columns/layout', query_string={'vista': vista}).json == (cambio if permitido else original)
    finally:
        cambiar_rol(auth_client, 'zeno')
        auth_client.post('/api/columns/layout', json={'vista': vista, 'columns': []})
        if creado:
            with app.app_context():
                AccesoProyecto.query.filter_by(usuario_id=uid, proyecto_id=pid).delete()
                db.session.commit()
