import json
from datetime import datetime
from uuid import uuid4

import pytest

from db import db
from models import AppConfig, NucleusData, Proyecto
from services.cotizacion_numeracion import bloquear_config, reservar, siguiente


@pytest.fixture
def proyecto_numeracion(app):
    with app.app_context():
        proyecto = Proyecto(nombre='Numeracion test ' + uuid4().hex)
        db.session.add(proyecto)
        db.session.commit()
        pid = proyecto.id
    yield pid
    with app.app_context():
        db.session.rollback()
        NucleusData.query.filter_by(proyecto_id=pid).delete()
        AppConfig.query.filter_by(proyecto_id=pid).delete()
        db.session.delete(db.session.get(Proyecto, pid))
        db.session.commit()


def guardar(pid, key, orden, numero=None):
    db.session.add(NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps({
        'N° COTIZACION': numero or key, 'N° ORDEN': str(orden)})))
    db.session.commit()


@pytest.mark.parametrize('prefijo', ['EN', 'CL', 'IN', 'PX'])
def test_sugerencia_vieja_no_reutiliza_numero_de_otro_cliente(app, proyecto_numeracion, prefijo):
    with app.app_context():
        pid = proyecto_numeracion
        guardar(pid, 'PX-2026-10-000528', 452)
        key, orden = reservar(pid, prefijo, datetime(2026, 10, 29), f'{prefijo}-2026-10-000527')
        assert key == f'{prefijo}-2026-10-000529'
        assert orden == '453'
        guardar(pid, key, orden)
        assert siguiente(pid, 2026) == 530


def test_sufijo_y_clave_original_reservan_el_consecutivo(app, proyecto_numeracion):
    with app.app_context():
        pid = proyecto_numeracion
        guardar(pid, 'CL-2026-10-000529', '456.1', 'CL-2026-10-000529.1')
        key, orden = reservar(pid, 'EN', datetime(2026, 10, 29), 'CL-2026-10-000529.1')
        assert key == 'EN-2026-10-000530'
        assert orden == '457'


def test_reserva_no_se_confirma_si_falla_el_alta(app, proyecto_numeracion):
    with app.app_context():
        pid = proyecto_numeracion
        cfg = bloquear_config(pid)
        cfg.valor = '530'
        db.session.commit()
        assert reservar(pid, 'CL', datetime(2026, 10, 29))[0].endswith('000530')
        db.session.rollback()
        assert siguiente(pid, 2026) == 530


def test_numero_manual_futuro_avanza_para_todos_los_clientes(app, proyecto_numeracion):
    with app.app_context():
        pid = proyecto_numeracion
        key, orden = reservar(pid, 'PX', datetime(2026, 10, 29), 'PX-2026-10-000550', manual=True)
        guardar(pid, key, orden)
        assert reservar(pid, 'CL', datetime(2026, 10, 29)) == ('CL-2026-10-000551', '2')
        db.session.rollback()


def test_eliminar_ultimo_caso_no_reutiliza_numero_ni_orden(app, proyecto_numeracion):
    with app.app_context():
        pid = proyecto_numeracion
        key, orden = reservar(pid, 'CL', datetime(2026, 10, 29))
        guardar(pid, key, orden)
        NucleusData.query.filter_by(proyecto_id=pid, key_value=key).delete()
        db.session.commit()
        assert reservar(pid, 'PX', datetime(2026, 10, 29)) == ('PX-2026-10-000031', '2')
        db.session.rollback()


def test_configuracion_no_baja_y_numero_recuperado_no_rompe_editor(app, auth_client):
    from services.utilidades import ahora_peru
    year = ahora_peru().year
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        cfg = bloquear_config(pid)
        original = cfg.valor
        cfg.valor = '9000100'
        key = f'CL-{year}-10-9000099'
        guardar(pid, key, 9000100, key + '.1')
    auth_client.get(f'/switch_project/{pid}')
    try:
        response = auth_client.post('/api/cotizacion/next_seq', json={'next': 99})
        assert response.status_code == 400
        assert response.json['minimum'] >= 9000100
        assert auth_client.post('/api/rows/update', json={
            'key': key, 'field': 'N° COTIZACION', 'value': key + '.1'}).status_code == 200
        assert auth_client.post('/api/rows/update', json={
            'key': key, 'field': 'N° ORDEN', 'value': '1'}).status_code == 400
        assert auth_client.post('/api/rows/edit_key', json={
            'old_key': key, 'new_key': key + '.2'}).status_code == 400
    finally:
        with app.app_context():
            db.session.rollback()
            NucleusData.query.filter_by(proyecto_id=pid, key_value=key).delete()
            AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_seq').one().valor = original
            db.session.commit()


def test_health_identifica_el_despliegue_compatible(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.headers['X-Nucleus-Cotizacion-Sequence'] == 'v2'
