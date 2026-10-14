# -*- coding: utf-8 -*-
"""Tests del dashboard comercial de Cotizaciones (/analytics/cotizaciones).

Cubre el parser de montos, el mapa de pestañas (idéntico al backend), los
agregados del servicio y que la ruta responde sin tocar el dashboard operativo.
"""
import json
from datetime import date

from db import db
from models import Proyecto, NucleusData
from services.dashboard_cotizaciones import indicadores, _pestania, _en_proveedor, _money


# ── Parser de montos ──────────────────────────────────────────────────────────
def test_money_formatos():
    assert _money('1050.00') == 1050.0
    assert _money('1,234.56') == 1234.56
    assert _money('S/ 105.00') == 105.0
    assert _money('1.234,56') == 1234.56
    assert _money(None) == 0.0
    assert _money('') == 0.0
    assert _money('sin datos') == 0.0


# ── Pestaña calculada igual que el backend ────────────────────────────────────
def test_pestania_mapea_igual_que_el_backend():
    assert _pestania({'ESTADO COTIZACION': 'Pdt. Cotización'}) == 'registro'
    assert _pestania({'ESTADO COTIZACION': 'En Aprobación'}) == 'cliente'
    assert _pestania({'ESTADO COTIZACION': 'Cotizado'}) == 'cliente'
    assert _pestania({'ESTADO COTIZACION': 'Aprobado'}) == 'sustentar'
    assert _pestania({'ESTADO COTIZACION': 'Atendido'}) == 'atendido'
    assert _pestania({'ESTADO COTIZACION': 'Validado'}) == 'atendido'
    assert _pestania({'ESTADO COTIZACION': 'Cancelado'}) == 'cancelado'
    assert _pestania({'ESTADO COTIZACION': 'Anulado'}) == 'cancelado'
    assert _pestania({'ESTADO COTIZACION': ''}) == 'registro'
    assert _pestania({}) == 'registro'


def test_en_proveedor_flags():
    assert _en_proveedor({'ESTADO COTIZACION': 'Aprobado'})
    assert _en_proveedor({'ESTADO COTIZACION': 'Atendido'})
    assert _en_proveedor({'ESTADO COTIZACION': 'Registro', '_PROVEEDOR_PARALELO': True})
    assert _en_proveedor({'ESTADO COTIZACION': 'Registro', 'FECHA APROBACION': '2026-01-01'})
    assert not _en_proveedor({'ESTADO COTIZACION': 'Pdt. Cotización'})


# ── Agregados ─────────────────────────────────────────────────────────────────
def _fila(key, estado, **extra):
    d = {'_key': key, 'ESTADO COTIZACION': estado}
    d.update(extra)
    return d


def test_indicadores_detalle():
    rows = [
        _fila('A1', 'Pdt. Cotización', **{'SUB TOTAL + FEE': '100.50',
              'FECHA': '2026-10-01 09:00', 'GESTOR': 'maria', 'CLIENTE': 'ENTEL'}),
        _fila('A2', 'En Aprobación', **{'SUB TOTAL + FEE': '200',
              'FECHA': '01/10/2026', 'COTIZADO POR': 'hvargas'}),
        _fila('A3', 'Atendido', **{'SUBTOTAL FACTURA PROVEEDOR': '50',
              'FECHA': '2026-10-03', 'FECHA ATENCION': '2026-10-05 10:00',
              'ADJUNTO FACTURA PROVEEDOR': '/api/x/factura.pdf'}),
        _fila('A4', 'Aprobado', **{'FECHA APROBACION': '2026-10-01 08:00',
              'SOLICITADO POR': 'laracca'}),
    ]
    d = indicadores(rows, hoy=date(2026, 10, 10))
    assert d['total'] == 4
    assert d['monto_total'] == 300.50

    a1, a2, a3, a4 = d['detalle']
    assert a1['mes'] == '2026-10' and a1['dia'] == '2026-10-01' and a1['pestania'] == 'registro'
    # FECHA en formato dd/mm/yyyy también se entiende
    assert a2['mes'] == '2026-10'
    # 'genero' cae a COTIZADO POR; en A1 (sin) cae al gestor
    assert a2['genero'] == 'hvargas'
    assert a1['genero'] == 'maria'
    # Atendido: pestaña correcta, en proveedor, factura detectada
    assert a3['pestania'] == 'atendido' and a3['proveedor'] and a3['factura_ok']
    assert a3['facturado'] == 50.0
    # Sustentar: aging en días y solicitante con fallback
    assert a4['pestania'] == 'sustentar' and a4['aging'] == 9 and a4['solicito'] == 'laracca'


def test_indicadores_vacio_y_fechas_malas():
    d = indicadores([{'_key': 'X', 'FECHA': 'no es fecha'}, 'no-dict'], hoy=date(2026, 10, 10))
    assert d['total'] == 1
    assert d['detalle'][0]['mes'] == '' and d['detalle'][0]['dia'] == ''
    assert d['detalle'][0]['pestania'] == 'registro'


# ── Ruta ──────────────────────────────────────────────────────────────────────
def test_ruta_dashboard_cotizaciones(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value='DASH-COT-TEST',
                                   data_json=json.dumps({'ESTADO COTIZACION': 'En Aprobación',
                                                         'SUB TOTAL + FEE': '10',
                                                         'COTIZADO POR': 'hvargas',
                                                         'CLIENTE': 'ENTEL',
                                                         'FECHA': '2026-10-08 14:01'})))
        db.session.commit()
        try:
            r = auth_client.get('/analytics/cotizaciones')
            assert r.status_code == 200, r.status_code
            assert 'Pipeline de cotizaciones' in r.get_data(as_text=True)
            assert 'DASH-COT-TEST' in r.get_data(as_text=True)
            # El dashboard operativo no cambia.
            r2 = auth_client.get('/analytics')
            assert r2.status_code in (200, 302)
        finally:
            NucleusData.query.filter_by(proyecto_id=pid, key_value='DASH-COT-TEST').delete()
            db.session.commit()


def test_ruta_dashboard_cotizaciones_login_requerido(client):
    r = client.get('/analytics/cotizaciones')
    assert r.status_code in (301, 302)
