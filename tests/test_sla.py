"""Módulo SLA: casos de FLM con su inicio según el tipo, objetivo y técnico."""
import json

from db import db
from models import NucleusData, Proyecto


def test_sla_claro_calcula_inicio_por_tipo(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        filas = [NucleusData(proyecto_id=pid, key_value=k, data_json=json.dumps(d)) for k, d in (
            ('CM-T-1', {'Ticket Id': 'CM-T-1', 'Task Type': 'CM', 'Dispatch Time': '2026-11-10 08:00:00', 'Arrive Time': '2026-11-10 09:00:00',
                        'Complete Time': '2026-11-10 11:00:00', 'SLA Hour': '240', 'SLA Status': 'normal', 'Schedule Operator': 'E1234567',
                        'Create Operator ID': 'E1234567', 'Create Operator': 'JUAN PEREZ'}),
            ('PM-T-2', {'Ticket Id': 'PM-T-2', 'Task Type': 'PM', 'Dispatch Time': '2026-11-10 08:00:00', 'Arrive Time': '2026-11-10 09:30:00',
                        'SLA Hour': '150', 'SLA Status': 'normal', 'Schedule Operator': 'E7654321'}),
            ('PLM-T-3', {'Ticket Id': 'PLM-T-3', 'Task Status': 'canceled', 'Task Type': 'PLM'}))]
        db.session.add_all(filas); db.session.commit()
        ids = [f.id for f in filas]
    try:
        assert auth_client.get('/sla/').status_code == 200
        casos = {c['ticket']: c for c in auth_client.get('/api/sla/claro').json['casos']}
        assert casos['CM-T-1']['inicio'] == '2026-11-10 08:00:00' and casos['CM-T-1']['objetivo'] == 240  # CM: Dispatch Time
        assert casos['CM-T-1']['tecnico_nombre'] == 'Juan Perez'
        assert casos['PM-T-2']['inicio'] == '2026-11-10 09:30:00' and casos['PM-T-2']['fin'] == ''  # PM: Arrive Time, abierto
        assert 'PLM-T-3' not in casos  # cancelados fuera
        assert auth_client.get('/api/sla/otro').status_code == 404
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False); db.session.commit()
