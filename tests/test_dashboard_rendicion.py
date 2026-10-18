# -*- coding: utf-8 -*-
"""Tests del dashboard de Rendición (/analytics/rendicion).

Además de los agregados, verifica que el mapa estado→pestaña del servicio siga
siendo IDÉNTICO al de blueprints/rendicion.py: si alguien cambia el flujo y no
el dashboard (o al revés), este test lo delata.
"""
import json
from datetime import date

from db import db
from models import Proyecto, NucleusData
from services.dashboard_rendicion import indicadores, _estado_de, _etapa_de


def test_etapa_coincide_con_el_blueprint():
    from blueprints.rendicion import _estado_de as bp_estado, _etapa_de as bp_etapa
    casos = [
        {}, {'ESTADO': ''}, {'ESTADO': 'PENDIENTE'}, {'ESTADO': 'VALIDADO'},
        {'ESTADO': 'DEPOSITADO'}, {'ESTADO': 'CON SUSTENTO'}, {'ESTADO': 'OBSERVADO'},
        {'ESTADO': 'SUSTENTADO'}, {'ESTADO': 'ARCHIVADO'}, {'ESTADO': 'ANULADO'},
        {'ESTADO': 'RECHAZADO'}, {'ESTADO': 'RECHAZADO', '_RECHAZO_ETAPA': 'VALIDACION'},
        {'ESTADO': 'RECHAZADO', '_RECHAZO_ETAPA': 'EVIDENCIA'},
        {'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'VALIDADO'},
        {'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'DEPOSITADO'},
        {'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'CON SUSTENTO'},
        {'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'OBSERVADO'},
        {'ESTADO': 'RECHAZADO', 'RECHAZADO DESDE': 'OTRA COSA'},
        {'ESTADO': 'basura'},
    ]
    for caso in casos:
        assert _estado_de(caso) == bp_estado(caso), caso
        assert _etapa_de(caso) == bp_etapa(caso), caso


def _fila(key, estado, **extra):
    d = {'_key': key, 'ESTADO': estado}
    d.update(extra)
    return d


def test_indicadores_detalle():
    rows = [
        _fila('R1', '', **{'Marca temporal': '29/9/2026 15:45:43', 'Monto total del depósito': '70.36',
                           'Nombre de site': 'NUEVO COMAS', 'Nombre del proyecto': 'Integratel',
                           'Tipo de presupuesto': 'NO REFACTURABLE', 'Tipo de gasto': 'Movilidad'}),
        _fila('R2', 'VALIDADO', **{'Marca temporal': '2026-10-01 10:00', 'Monto total del depósito': '100',
                                   'VALIDADO POR': 'n_flm'}),
        _fila('R3', 'DEPOSITADO', **{'Marca temporal': '2026-10-02 10:00', 'Monto total del depósito': '200',
                                     'MONTO PAGO': '180', 'FOTO PAGO': '/x/foto.jpg', 'DEPOSITADO POR': 'hvargas'}),
        _fila('R4', 'SUSTENTADO', **{'Marca temporal': '2026-10-03 10:00', 'Monto total del depósito': '50'}),
    ]
    d = indicadores(rows, hoy=date(2026, 10, 10))
    assert d['total'] == 4
    # monto = pagado si existe, si no el solicitado
    assert d['monto_total'] == 70.36 + 100 + 180 + 50

    r1, r2, r3, r4 = d['detalle']
    assert r1['etapa'] == 'VALIDACION' and r1['estado'] == 'PENDIENTE'
    assert r1['mes'] == '2026-09' and r1['dia'] == '2026-09-29'
    assert r1['aging'] == 11
    assert r2['etapa'] == 'DEPOSITOS' and r2['valido_por'] == 'n_flm'
    assert r3['etapa'] == 'EVIDENCIA' and r3['pagado'] == 180.0 and r3['foto_pago'] is True
    assert r4['etapa'] == 'ATENDIDO' and r4['aging'] is None


def test_indicadores_vacio_y_fecha_mala():
    d = indicadores([{'_key': 'X', 'Marca temporal': 'no es fecha'}, 'no-dict'], hoy=date(2026, 10, 10))
    assert d['total'] == 1
    assert d['detalle'][0]['mes'] == '' and d['detalle'][0]['etapa'] == 'VALIDACION'


def test_ruta_dashboard_rendicion(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Rendicion').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value='DASH-REND-TEST',
                                   data_json=json.dumps({'ESTADO': 'VALIDADO',
                                                         'Marca temporal': '2026-10-02 10:00',
                                                         'Monto total del depósito': '123.45',
                                                         'Nombre del proyecto': 'Integratel'})))
        db.session.commit()
        try:
            r = auth_client.get('/analytics/rendicion')
            assert r.status_code == 200, r.status_code
            html = r.get_data(as_text=True)
            assert 'Dónde se queda cada caso' in html
            assert 'DASH-REND-TEST' in html
            # El selector de dashboard y la hoja compartida deben estar en las tres vistas.
            assert 'dash-switch' in html
            for ruta in ('/analytics', '/analytics/cotizaciones', '/analytics/rendicion'):
                pagina = auth_client.get(ruta).get_data(as_text=True)
                assert 'dash-switch' in pagina, ruta
                assert 'analytics-comun.css' in pagina, ruta
            # La barra de recursos del FLM no debe aparecer en ninguna vista de Analytics.
            # Los catálogos ahora tienen accesos propios en el menú de módulos.
            # Con un FLM como proyecto actual, la comprobación
            # de abajo no probaría nada.
            flm = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
            if flm:
                auth_client.get('/switch_project/%s' % flm.id)
                html = auth_client.get('/configuraciones').get_data(as_text=True)
                assert 'flm-resource-bar' not in html
                assert 'sidebar-link-text">Personal</span>' in html
                for ruta in ('/analytics', '/analytics/cotizaciones', '/analytics/rendicion'):
                    assert 'flm-resource-bar' not in auth_client.get(ruta).get_data(as_text=True), ruta
        finally:
            NucleusData.query.filter_by(proyecto_id=pid, key_value='DASH-REND-TEST').delete()
            db.session.commit()


def test_ruta_dashboard_rendicion_login_requerido(client):
    r = client.get('/analytics/rendicion')
    assert r.status_code in (301, 302)
