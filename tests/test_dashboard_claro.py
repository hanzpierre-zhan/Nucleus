import json
from services.dashboard_claro import indicadores
from db import db
from models import Proyecto,NucleusData


def test_datos_reales_sin_inventar_sla_o_cierre():
    d=indicadores([{'Ticket Id':'CM-1','Task Status':'completed','Create Time':'2026-10-01 10:00:00','Complete Time':'2026-10-02 12:00:00','SLA Status':'sla_violation'},
                   {'Ticket Id':'PM-2','Task Status':'inprocess','Complete Time':'2026-10-02','SLA Status':''}, {'_key':'123456'}])
    assert d['total']==2 and d['sin_identificador']==1
    assert d['rows'][0]['sla'] is False
    assert d['rows'][1]['cierre'] is None and d['rows'][1]['sla'] is None


def test_dashboard_claro_lee_solo_claro(app,auth_client):
    with app.app_context():
        p=Proyecto.query.filter_by(nombre='FLM - CLARO').one()
        row=NucleusData(proyecto_id=p.id,key_value='CL-DASH-QA',data_json=json.dumps({'Ticket Id':'CL-DASH-QA','Create Time':'2026-10-01','Task Status':'completed'}))
        db.session.add(row);db.session.commit();rid=row.id
    try:
        r=auth_client.get('/analytics/claro?vista=clasica');assert r.status_code==200
        assert b'CL-DASH-QA' in r.data and b'cl-evolucion' in r.data
    finally:
        with app.app_context():db.session.delete(db.session.get(NucleusData,rid));db.session.commit()


def test_mismo_formato_para_integratel_y_entel():
    from services.dashboard_claro import region
    i=indicadores([{'Task Id':'CM-1','Task Status':'inprocess','Createtime':'2026-10-01 10:00:00','First Complete Time':'2026-10-01 12:00:00',
                    'Sla Status':'normal','Fm Office':'HUAWEI CENTRO ICA','FME contrator':'COBRA'}],'INTEGRATEL')['rows'][0]
    # Reabierto: para el SLA ya cerró en el primer cierre.
    assert i['completado'] and i['cierre'].startswith('2026-10-01T12') and i['sla'] is True and i['region']=='CENTRO' and i['proveedor']=='COBRA'
    e=indicadores([{'Task ID(create)':'CM-2','Ticket Status':'Completed','CreateTime(create)':'2026-10-01 10:00:00','SubmitTime(complete)':'2026-10-02 10:00:00',
                    'SLA Status':'sla_violation','fm_office':'ICA_REGIÓN SUR','Contractor':'COBRA','Region Manager(create)':'RM 1','Associate OrderId':'INC-1'}],'ENTEL')
    r=e['rows'][0]
    assert r['tipo']=='CM' and r['sla'] is False and r['region']=='SUR' and r['rm']=='RM 1' and not r['hijo'] and e['con_rm']
    c=indicadores([{'Ticket Id':'CM-3','Task Status':'completed','SLA Status':'milestone_broken','associateorderid':'CM-9;INC-1'}])['rows'][0]
    assert c['sla'] is False and c['hijo']
    assert region('FM Office LIMA SUR')=='LIMA' and region('Default FM Office')=='Sin región'


def test_integratel_y_entel_usan_dashboard_sla(app,auth_client):
    for ruta in ('/analytics/integratel','/analytics/entel'):
        r=auth_client.get(ruta)
        if r.status_code==200:
            assert b'cl-evolucion' in r.data and b'vista=clasica' in r.data
