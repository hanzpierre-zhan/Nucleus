import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from services.dashboard_cotizaciones import indicadores as cotizaciones
from services.dashboard_rendicion import indicadores as rendiciones


def test_rendicion_separa_validadores_solicitante_y_pago_cero():
    r = rendiciones([{'_key': 'R1', 'ESTADO': 'DEPOSITADO', 'Marca temporal': '2026-09-01',
                      'Nombre del proyecto': 'Entel - Pext', 'DEPARTAMENTO': 'Ica',
                      'Monto total del depósito': '100', 'MONTO PAGO': 0, 'FECHA PAGO': '2026-10-05',
                      'Responsable de la validación': 'asignado', 'VALIDADO POR': 'efectivo',
                      'INTERACCION': 'ultimo_actor', 'Supervisor encargado': 'supervisor'}], hoy=date(2026, 10, 10))['detalle'][0]
    assert r['pagado'] == r['monto'] == 0 and r['solicitado'] == 100
    assert r['pago_registrado'] and r['depositado']
    assert r['responsable_validacion'] == 'asignado' and r['valido_por'] == 'efectivo'
    assert r['solicito'] == 'Sin datos' and r['registrador'] == 'Sin registrador'
    assert r['ultimo_interactor'] == 'ultimo_actor'
    assert r['departamento'] == 'Ica' and r['proyecto'] == 'FLM - PEXT'
    assert r['dias_etapa'] == 5 and r['fuente_fecha_etapa'] == 'FECHA PAGO'


def test_rendicion_con_sustento_no_se_considera_cerrada_y_no_inventa_fecha():
    rows = [{'ESTADO': s, 'Marca temporal': '2026-09-01', 'MONTO PAGO': '50', 'FECHA SUSTENTO': '2026-10-09'}
            for s in ('CON SUSTENTO', 'SUSTENTADO', 'ARCHIVADO')]
    pendientes, cerrado, archivado = rendiciones(rows, hoy=date(2026, 10, 10))['detalle']
    assert pendientes['situacion'] == 'Sustento cargado · pendiente de validación'
    assert pendientes['dias_etapa'] is None and not pendientes['cerrado']
    assert cerrado['cerrado'] and archivado['cerrado']
    assert cerrado['dias_etapa'] is None  # No siguen envejeciendo casos cerrados.


def test_espera_usa_la_ultima_transicion_real_incluso_al_revertir():
    base = {'ESTADO': 'PENDIENTE', 'Marca temporal': '2026-09-01',
            '_HISTORIAL_FLUJO': [{'hasta': 'PENDIENTE', 'fecha': '2026-10-08'}]}
    r = rendiciones([base], hoy=date(2026, 10, 10))['detalle'][0]
    assert r['dias_etapa'] == 2 and r['fuente_fecha_etapa'] == '_HISTORIAL_FLUJO'
    base['_HISTORIAL_FLUJO'][0]['fecha'] = ''
    assert rendiciones([base], hoy=date(2026, 10, 10))['detalle'][0]['dias_etapa'] is None


def test_cotizacion_no_mezcla_gastos_ingresos_y_fechas():
    source = {'ESTADO COTIZACION': 'En Aprobación', 'CLIENTE': 'PEXT', 'SUB TOTAL + FEE': '120',
              'TIPO DE GASTO': 'Gasto Cobra', 'TIPO GASTO APROBACION': 'Proveedor',
              'FECHA': '2026-09-01', 'FECHA ENVIO CLIENTE': '2026-10-07',
              'SOLICITADO POR': 'solicito', 'COTIZADO POR': 'genero', 'CREADO POR': 'registro'}
    before = dict(source)
    d = cotizaciones([source], hoy=date(2026, 10, 10))
    r = d['detalle'][0]
    assert r['gasto'] == 'Gasto Cobra' and r['gasto_aprobacion'] == 'Proveedor'
    assert not r['proveedor']  # Vista proveedor solo después de aprobar.
    assert r['solicito'] == 'solicito' and r['genero'] == 'genero' and r['registrador'] == 'registro'
    assert r['dias_etapa'] == 3 and r['dia_solicitud'] == '2026-09-01'
    assert r['situacion'] == 'En aprobación · pendiente del cliente'
    assert not d['ingreso_disponible'] and 'ingreso' not in r
    assert source == before


def test_cotizacion_timestamp_validado_no_se_confunde_con_una_bandera():
    def row(estado, validacion):
        return {'ESTADO COTIZACION': estado, '_SUSTENTO_VALIDADO': validacion}
    r = cotizaciones([row('Aprobado', '2026-10-08 10:00'), row('Atendido', '0'),
                      row('Atendido', '2026-10-08 10:00')], hoy=date(2026, 10, 10))['detalle']
    assert r[0]['sustento_ok'] and r[0]['situacion'] == 'Sustento validado · pendiente de cierre'
    assert not r[1]['sustento_ok'] and 'sin validación' in r[1]['situacion']
    assert r[2]['sustento_ok'] and 'validado y atendido' in r[2]['situacion']


def test_fecha_futura_no_produce_espera_negativa():
    r = cotizaciones([{'ESTADO COTIZACION': 'Aprobado', 'FECHA APROBACION': '2027-01-01'}], hoy=date(2026, 10, 10))['detalle'][0]
    assert r['dias_etapa'] is None and 'futura' in r['fuente_fecha_etapa']


def test_matriz_js_cuenta_una_vez_el_proveedor_y_conserva_totales():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node no está instalado')
    code = """const {aggregate}=require(process.argv[1]);
    const rows=JSON.parse(process.argv[2]);const r=aggregate(rows,'proyecto','monto');
    console.log(JSON.stringify({n:r.n,amount:r.amount,groups:r.groups.map(g=>({n:g.n,amount:g.amount,cells:[...g.cells]}))}));"""
    rows = [{'proyecto': 'PEXT', 'situacion': 'Aprobado', 'monto': 100, 'proveedor': True, 'dias_etapa': 3},
            {'proyecto': 'PEXT', 'situacion': 'Atendido', 'monto': 200, 'proveedor': True, 'dias_etapa': None},
            {'proyecto': 'CLARO', 'situacion': 'Cliente', 'monto': 0, 'dias_etapa': None}]
    out = subprocess.run([node, '-e', code, str(Path('static/js/dashboard-consulta.js').resolve()), json.dumps(rows)],
                         capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    assert result['n'] == 3 and result['amount'] == 300
    assert sum(g['n'] for g in result['groups']) == 3
    assert result['groups'][0]['n'] == 2


def test_sustento_usa_fecha_real_del_formulario():
    r = rendiciones([{'ESTADO': 'CON SUSTENTO', 'SUSTENTO_MARCA TEMPORAL': '2026-10-08',
                       'Marca temporal': '2026-01-01'}], hoy=date(2026, 10, 10))['detalle'][0]
    assert r['dias_etapa'] == 2
