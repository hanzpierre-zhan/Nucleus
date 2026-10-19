from copy import deepcopy
from datetime import datetime
import json

import pytest

from scripts.conciliar_cotizaciones_anton import adaptar, conciliar, numero_px


@pytest.mark.parametrize('original,esperado,pestania', [
    ('Pendiente de Aprobacion', 'En Aprobación', 'cliente'),
    ('Cotización Rechazada', 'Rechazado', 'registro'),
])
def test_estados_equivalentes_en_flujo_y_dashboard(original, esperado, pestania):
    from blueprints.cotizacion import _cot_pestania
    from services.dashboard_cotizaciones import _pestania
    row = {'ESTADO COTIZACION': original, 'ITEMS_JSON': '[{"cantidad":2}]',
           'SUB TOTAL + FEE': '123.45', 'GENERADA': '1'}
    copia = deepcopy(row)
    result = adaptar(row)
    assert not result['incidencias']
    assert result['datos']['ESTADO COTIZACION'] == esperado
    assert _cot_pestania(result['datos']) == _pestania(result['datos']) == pestania
    assert result['datos']['ITEMS_JSON'] == row['ITEMS_JSON']
    assert result['datos']['SUB TOTAL + FEE'] == '123.45'
    assert row == copia


def test_conciliacion_no_retrocede_aprobaciones_y_detecta_otra_wo():
    row = {'ESTADO COTIZACION': 'Pendiente de Aprobacion', 'CLIENTE': 'ENTEL',
           'NUMERO WO': 'CM-1', 'ITEMS_JSON': '[]'}
    actual = {**row, 'ESTADO COTIZACION': 'Atendido', 'ADJUNTO CORREO CLIENTE': 'correo.msg'}
    copia = deepcopy(actual)
    assert conciliar(row, actual)['accion'] == 'conservar_nucleus'
    assert actual == copia
    assert conciliar(row, {**actual, 'NUMERO WO': 'CM-2'})['accion'] == 'revisar_colision_de_clave'


def test_estados_desconocidos_e_items_invalidos_bloquean_carga():
    row = {'ESTADO COTIZACION': 'Inesperado', 'ITEMS_JSON': '{roto'}
    result = conciliar(row, None)
    assert result['accion'] == 'bloqueado_por_validacion'
    assert result['adaptacion']['incidencias'] == ['estado_sin_equivalencia', 'items_invalidos']
    assert result['adaptacion']['datos'] == row


def test_numeracion_px_diferencia_colisiones_sin_cambiar_sufijo_original():
    ocupados = {'px-2026-001'}
    assert numero_px('EN-2026-001', ocupados) == 'PX-2026-001-02'
    assert numero_px('CL-2026-001', ocupados) == 'PX-2026-001-03'
    assert numero_px('HW-2025-009', ocupados) == 'PX-2025-009'
    assert numero_px('PX-2026-010', ocupados) == 'PX-2026-010'
    with pytest.raises(ValueError):
        numero_px('', ocupados)


def test_no_envia_a_cliente_un_documento_sin_constancia_de_generacion():
    result = adaptar({'ESTADO COTIZACION': 'Pendiente de Aprobacion', 'ITEMS_JSON': '[]'})
    assert result['datos']['ESTADO COTIZACION'] == 'Pdt. Cotización'
    assert result['advertencias'] and not result['incidencias']


def test_remapea_rutas_serializadas_sin_tocar_descripciones():
    row = {'ESTADO COTIZACION': 'Pendiente de Aprobacion', 'ITEMS_JSON': '[]',
           'fotos': '["/api/evidencia/foto/2/WO/inicio.jpg"]', 'OBJETIVO': 'Proyecto 2'}
    result = adaptar(row, {2: 19})
    assert '/foto/19/' in result['datos']['fotos']
    assert result['datos']['OBJETIVO'] == 'Proyecto 2'


@pytest.fixture
def documento_guardado(app):
    from db import db
    from models import Proyecto, Cotizacion
    with app.app_context():
        p = Proyecto.query.filter_by(nombre='FLM - PEXT').one()
        row = Cotizacion(proyecto_id=p.id, key_value='ANTON-TEST-WO', numero='HW-TEST',
            nota='Prueba histórica', cotizado_por='Autor original', revisado_por='Revisor original',
            gastos_json='[{"descripcion":"Material","total_p":15}]', mano_obra_json='[]',
            fecha_generacion=datetime(2026, 9, 1, 12, 30), bloqueada=True, formato='')
        db.session.add(row)
        db.session.commit()
        cid, pid = row.id, p.id
    yield cid, pid
    with app.app_context():
        db.session.delete(db.session.get(Cotizacion, cid))
        db.session.commit()


def test_descarga_pext_preserva_documento_fecha_autores_y_formato(app, auth_client, documento_guardado, monkeypatch):
    import blueprints.cotizacion as modulo
    from db import db
    from models import Cotizacion
    cid, pid = documento_guardado
    auth_client.get('/switch_project/%s' % pid)
    received = {}
    def pdf(**kwargs):
        received.update(kwargs)
        return b'%PDF-1.4\nprueba'
    monkeypatch.setattr(modulo, '_generar_pdf_cotizacion', pdf)
    result = auth_client.get('/api/cotizacion/descargar', query_string={'key': 'ANTON-TEST-WO', 'cotizacion_id': cid})
    assert result.status_code == 200
    assert result.content_type == 'application/pdf'
    assert received['fecha'] == '01/09/2026'
    assert received['cotizado_por'] == 'Autor original'
    assert received['gastos'][0]['total_p'] == 15
    with app.app_context():
        r = db.session.get(Cotizacion, cid)
        assert r.formato == '' and r.bloqueada
        assert r.fecha_generacion == datetime(2026, 9, 1, 12, 30)
        assert r.cotizado_por == 'Autor original'
    assert auth_client.get('/api/cotizacion/descargar', query_string={'key': 'OTRA-WO', 'cotizacion_id': cid}).status_code == 404
    auth_client.get('/switch_project/1')
    # El documento no se puede descargar desde otro proyecto.
    with auth_client.session_transaction() as session:
        session['current_proyecto_id'] = pid + 1000
    assert auth_client.get('/api/cotizacion/descargar', query_string={'key': 'ANTON-TEST-WO', 'cotizacion_id': cid}).status_code == 404


@pytest.mark.parametrize('formato', ['', 'cobra'])
def test_pdf_real_admite_ambos_formatos_guardados(app, auth_client, documento_guardado, formato):
    from db import db
    from models import Cotizacion
    cid, pid = documento_guardado
    with app.app_context():
        row = db.session.get(Cotizacion, cid)
        row.formato = formato
        row.items_json = json.dumps([{'tipo': 'SERVICIO', 'texto': 'Prueba', 'und': 'UND',
                                     'cantidad': 1, 'valor_unitario': 15, 'valor_total': 15}])
        db.session.commit()
    auth_client.get('/switch_project/%s' % pid)
    response = auth_client.get('/api/cotizacion/descargar', query_string={
        'key': 'ANTON-TEST-WO', 'cotizacion_id': cid})
    assert response.status_code == 200
    assert response.data.startswith(b'%PDF-') and len(response.data) > 1000


def test_flujo_pext_funciona_con_nombre_canonico_y_conserva_bloqueo(app, auth_client):
    from db import db
    from models import Proyecto, NucleusData, HistorialCambios
    key = 'ANTON-FLUJO-PEXT-TEST'
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - PEXT').one().id
        row = NucleusData(proyecto_id=pid, key_value=key,
                          data_json=json.dumps({'CATEGORY': 'O&M PEXT', 'Numero de WO': key}))
        db.session.add(row)
        db.session.commit()
    try:
        auth_client.get('/switch_project/%s' % pid)
        response = auth_client.post('/api/rows/finalizar', json={'key': key, 'finalizado': True})
        assert response.status_code == 200, response.json
        with auth_client.session_transaction() as session:
            session['rol'] = 'contrata'
        bloqueado = auth_client.post('/api/rows/update', json={'key': key, 'field': 'MOTIVO', 'value': 'Cambio'})
        assert bloqueado.status_code == 403
        with auth_client.session_transaction() as session:
            session['rol'] = 'zeno'
        assert auth_client.post('/api/rows/finalizar', json={'key': key, 'finalizado': False}).status_code == 200
        response = auth_client.post('/api/wo/enviar_aprobacion', json={'key': key, 'accion': 'enviar'})
        assert response.status_code == 200, response.json
    finally:
        with app.app_context():
            HistorialCambios.query.filter_by(proyecto_id=pid, key_value=key).delete()
            NucleusData.query.filter_by(proyecto_id=pid, key_value=key).delete()
            db.session.commit()
