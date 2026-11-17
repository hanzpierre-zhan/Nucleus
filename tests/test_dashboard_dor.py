import json

from services.dashboard_dor import familia, indicadores


def test_solo_cm_y_campos_del_reporte():
    d = indicadores([
        {'Ticket Id': 'CM-1', 'Task Type': 'CM', 'Task Status': 'completed', 'Create Time': '2026-11-03 08:00:00', 'Dispatch Time': '2026-11-03 08:05:00',
         'Arrive Time': '2026-11-03 10:00:00', 'Complete Time': '2026-11-04 09:00:00', 'SLA Status': 'milestone_broken', 'FM Office': 'HUAWEI CENTRO ICA',
         'FME Contractor': 'COBRA', 'Root Cause': 'CORTE MAYOR A 12HRS', 'Suspend State': 'normal'},
        {'Ticket Id': 'CM-2', 'Task Type': 'CM', 'Task Status': 'inprocess', 'Create Time': '2026-11-05 08:00:00', 'Dispatch Time': '2026-11-05 08:01:00',
         'FM Office': 'HUAWEI LIMA OESTE', 'Suspend State': 'suspend', 'SLA Status': 'normal'},
        {'Ticket Id': 'CM-3', 'Task Type': 'CM', 'Task Status': 'Canceled', 'Create Time': '2026-11-06 08:00:00', 'Dispatch Time': '2026-11-06 08:01:00', 'FM Office': 'HUAWEI LIMA OESTE'},
        {'Ticket Id': 'PM-1', 'Task Type': 'PM', 'Task Status': 'completed'},
    ])
    assert d['total'] == 3 and d['hasta'] == '2026-11-06'
    a, b, c = d['rows']
    assert a['completado'] and a['sla'] is False and a['region'] == 'CENTRO' and a['familia'] == 'Corte de energía comercial' and a['cierre'].startswith('2026-11-04')
    assert b['cierre'] is None and b['parada'] and b['region'] == 'LIMA' and b['familia'] == 'Sin causa registrada'
    # Sin Cancel Time: se usa la fecha del despacho para ubicar la cancelación.
    assert c['cancelado'] and c['cancelacion'].startswith('2026-11-06')


def test_familias_de_causa():
    assert familia('ACTUA RESPALDO BATERIAS') == 'Baterías y autonomía'
    assert familia('FALSA ALARMA - CORTE ENERGIA') == 'Falsa alarma o sin falla'
    assert familia('VISITA TRUNCA') == 'Visita trunca'
    assert familia('DWDM-CAMBIO EQUIPAMIENTO') == 'Transmisión y fibra'


def test_pagina_operacion_diaria(app, auth_client):
    from db import db
    from models import NucleusData, Proyecto
    with app.app_context():
        p = Proyecto.query.filter_by(nombre='FLM - CLARO').one()
        row = NucleusData(proyecto_id=p.id, key_value='CM-DOR-QA', data_json=json.dumps({'Ticket Id': 'CM-DOR-QA', 'Task Type': 'CM', 'Create Time': '2026-11-01 10:00:00', 'Task Status': 'inprocess'}))
        db.session.add(row); db.session.commit(); rid = row.id
    try:
        r = auth_client.get('/analytics/claro/diario')
        assert r.status_code == 200 and b'CM-DOR-QA' in r.data and b'dor-sla' in r.data
    finally:
        with app.app_context():
            db.session.delete(db.session.get(NucleusData, rid)); db.session.commit()


def test_otros_proyectos_mismo_formato():
    i = indicadores([{'Task Id': 'CM-1', 'Task Type': 'CM', 'Task Status': 'inprocess', 'Createtime': '2026-11-01 10:00:00', 'Dispatch Time': '2026-11-01 10:05:00',
                      'First Complete Time': '2026-11-01 12:00:00', 'Sla Status': 'normal', 'Fm Office': 'HUAWEI CENTRO ICA', 'FME contrator': 'COBRA',
                      'Assign To Fme': 'T123', 'Assign To Fme Full Name': 'JUAN PEREZ', 'Com Fault Cause': 'AM - FALSO CONTACTO', 'Com Fault Speciality': 'ACCESO MOVIL'}], 'INTEGRATEL')['rows'][0]
    assert i['completado'] and i['sla'] is True and i['tecnico'] == 'JUAN PEREZ' and i['familia'] == 'ACCESO MOVIL' and i['region'] == 'CENTRO'
    e = indicadores([{'Task ID(create)': 'CM-2', 'Ticket Status': 'Completed', 'CreateTime(create)': '2026-11-01 10:00:00', 'dispatch_time': '2026-11-01 10:01:00',
                      'SubmitTime(complete)': '2026-11-01 15:00:00', 'SLA Status': 'sla_violation', 'fm_office': 'ICA_REGIÓN SUR', 'Contractor': 'COBRA',
                      'assign_to_fme': 'ANA RUIZ', 'Region Manager(create)': 'Harold Lopez', 'Task Category(create)': 'Pext', 'SLA Paused': 'YES'}], 'ENTEL')
    r = e['rows'][0]
    assert r['sla'] is False and r['rm'] == 'Harold Lopez' and r['region'] == 'SUR' and r['familia'] == 'Pext' and e['con_rm'] and e['etiquetas']['rm'] == 'Regional Manager'
    p = indicadores([{'Número de WO': 'CM-3', 'Estado de la tarea (WO State)': 'completed', 'Fecha de creación (WO Creation date)': '2026-11-01 08:00:00',
                      'Fecha y hora de WO a estado complete': '2026-11-01 20:00:00', 'Hrs Respuesta': '10hrs', 'Departamento': 'CALLAO',
                      'Nombre de personal FLM asignado': 'LUIS SOTO', 'Tipo tarea': 'CAIDA', 'Causa raíz': 'FO Cut'}], 'PEXT')['rows'][0]
    # 12 h contra 10 h de respuesta: fuera de SLA.
    assert p['sla'] is False and p['region'] == 'LIMA' and p['tecnico'] == 'LUIS SOTO' and p['familia'] == 'CAIDA'


def test_claro_tecnico_solo_nombre():
    r = indicadores([{'Ticket Id': 'CM-9', 'Task Type': 'CM', 'Task Status': 'inprocess', 'Assign To FME': 'E8410009'}])['rows'][0]
    assert r['tecnico'] == 'Sin técnico'
