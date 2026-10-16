# -*- coding: utf-8 -*-
"""Tests del Cuadro de Control de Cobranza (/analytics/cobranza).

El servicio consume el catálogo ya consolidado por el módulo Refacturable
(una fila por cotización aprobada). Aquí se prueban la normalización de
cliente, los indicadores derivados y que la ruta renderice con el selector
de dashboards compartido.
"""
import json
from datetime import date

from db import db
from models import Proyecto, NucleusData
from services.dashboard_cobranza import indicadores, _cliente, _tiene_evidencia


def test_cliente_canonico():
    assert _cliente('ENTEL') == 'ENTEL'
    assert _cliente('Claro') == 'CLARO'
    assert _cliente('CLARO, ENTEL') == 'MIXTO'
    assert _cliente('') == 'SIN CLIENTE'


def test_tiene_evidencia():
    assert _tiene_evidencia({'inicio': ['a'], 'proceso': [], 'cierre': []}) is True
    assert _tiene_evidencia({'inicio': [], 'proceso': [], 'cierre': []}) is False
    assert _tiene_evidencia(None) is False


def _reg(**extra):
    base = {
        'id': 1, 'cotizacion': 'HW-2026-0000001', 'correlativo': 'C-00000001',
        'nombre_proyecto': 'ENTEL', 'gestor': 'hvargas', 'numero_wo': 'WO1',
        'monto_cobra': '1000.00', 'monto_hw': '800.00',
        'documentos': {'sustento': 'Completo', 'factura': 'Pendiente',
                       'correo': 'No aplica', 'cotizacion': 'Completo'},
        'avance': 66, 'fotos': {'inicio': ['/e/1.jpg'], 'proceso': [], 'cierre': []},
        'numero_expense': 'E-1234', 'mes_cierre': '2026-10',
        'estado_cotizacion': 'Validado', 'estatus': 'Culminado',
        'estado_liquidacion': 'Aprobado',
    }
    base.update(extra)
    return base


def test_indicadores_detalle():
    d = indicadores([
        _reg(),
        _reg(id=2, cotizacion='HW-2026-0000002', nombre_proyecto='CLARO, ENTEL',
             numero_expense='', mes_cierre='', avance=100,
             documentos={'sustento': 'Completo', 'factura': 'Completo',
                         'correo': 'No aplica', 'cotizacion': 'Completo'},
             fotos={'inicio': [], 'proceso': [], 'cierre': []}),
        _reg(id=3, cotizacion='HW-2026-0000003', monto_cobra='', monto_hw='500.00'),
        'no-dict',
    ], hoy=date(2026, 10, 5))
    assert d['total'] == 3
    assert d['monto_total'] == 2500.0
    a, b, c = d['detalle']
    assert a['cliente'] == 'ENTEL' and a['con_evidencia'] is True
    assert a['con_expense'] is True and a['numero_expense'] == 'E-1234'
    assert a['completo'] is False and a['completos'] == 2 and a['no_aplica'] == 1
    assert a['margen'] == 200.0 and a['mes_cierre'] == '2026-10'
    assert b['cliente'] == 'MIXTO' and b['con_evidencia'] is False
    assert b['con_expense'] is False and b['completo'] is True and b['mes_cierre'] == ''
    # Sin monto manual, la plata cae al monto de la cotización (monto_hw).
    assert a['monto_manual'] is True and a['monto'] == 1000.0
    assert c['monto_manual'] is False and c['monto'] == 500.0 and c['monto_hw'] == 500.0


def test_ruta_dashboard_cobranza(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value='DASH-COB-TEST',
                                   data_json=json.dumps({'ESTADO COTIZACION': 'Validado',
                                                         'CLIENTE': 'ENTEL',
                                                         'N° COTIZACION': 'HW-COB-TEST',
                                                         'SUB TOTAL + FEE': '1500.00'})))
        db.session.commit()
        try:
            r = auth_client.get('/analytics/cobranza')
            assert r.status_code == 200, r.status_code
            html = r.get_data(as_text=True)
            assert 'Cuadro de control de cobranza' in html
            assert 'HW-COB-TEST' in html
            assert 'dash-switch' in html
            # El selector compartido debe aparecer en las cuatro vistas.
            for ruta in ('/analytics', '/analytics/cotizaciones',
                         '/analytics/rendicion', '/analytics/cobranza'):
                pagina = auth_client.get(ruta).get_data(as_text=True)
                assert 'dash-switch' in pagina, ruta
                assert 'Cobranza' in pagina, ruta
        finally:
            NucleusData.query.filter_by(proyecto_id=pid, key_value='DASH-COB-TEST').delete()
            db.session.commit()


def test_ruta_dashboard_cobranza_login_requerido(client):
    r = client.get('/analytics/cobranza')
    assert r.status_code in (301, 302)
