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
        r=auth_client.get('/analytics/claro');assert r.status_code==200
        assert b'CL-DASH-QA' in r.data and b'cl-evolucion' in r.data
    finally:
        with app.app_context():db.session.delete(db.session.get(NucleusData,rid));db.session.commit()
