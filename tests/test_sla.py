"""Módulo SLA: casos de FLM con su inicio según el tipo, objetivo y técnico."""
import json

from db import db
from models import NucleusData, Proyecto


def test_sla_claro_inicio_dispatch_y_cierre_por_task_status(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        filas = [NucleusData(proyecto_id=pid, key_value=k, data_json=json.dumps(d)) for k, d in (
            ('CM-T-1', {'Ticket Id': 'CM-T-1', 'Task Type': 'CM', 'Task Status': 'completed', 'Dispatch Time': '2026-11-10 08:00:00', 'Arrive Time': '2026-11-10 09:00:00',
                        'Complete Time': '2026-11-10 11:00:00', 'SLA Hour': '240', 'SLA Status': 'normal', 'Schedule Operator': 'E1234567', 'Task Category': 'Caida',
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
        assert casos['CM-T-1']['tecnico_nombre'] == 'Juan Perez' and casos['CM-T-1']['categoria'] == 'Caida'
        assert casos['CM-T-1']['dispatch'] == '2026-11-10 08:00:00' and casos['CM-T-1']['sla_hour'] == '240' and casos['CM-T-1']['sla_status_original'] == 'normal'
        assert casos['CM-T-1']['cerrado'] is True
        # PM/PLM cuentan desde Arrive Time; abierto mientras no esté completed.
        assert casos['PM-T-2']['inicio'] == '2026-11-10 09:30:00' and casos['PM-T-2']['cerrado'] is False
        assert 'PLM-T-3' not in casos  # cancelados fuera
        assert auth_client.get('/api/sla/otro').status_code == 404
        # Integratel aún no tiene criterios: no se calcula.
        r = auth_client.get('/api/sla/integratel').json
        assert r['pendiente'] is True and r['casos'] == []
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False); db.session.commit()


def test_alertas_por_vencer(app, auth_client):
    from datetime import datetime, timedelta
    from blueprints import sla
    ahora = datetime.utcnow() - timedelta(hours=5)
    inicio = lambda minutos: (ahora - timedelta(minutes=minutos)).strftime('%Y-%m-%d %H:%M:%S')
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        filas = [NucleusData(proyecto_id=pid, key_value=k, data_json=json.dumps(d)) for k, d in (
            ('CM-AL-1', {'Ticket Id': 'CM-AL-1', 'Task Type': 'CM', 'Dispatch Time': inicio(200), 'SLA Hour': '240'}),   # quedan 40 min
            ('CM-AL-2', {'Ticket Id': 'CM-AL-2', 'Task Type': 'CM', 'Dispatch Time': inicio(30), 'SLA Hour': '240'}),    # en plazo
            ('CM-AL-3', {'Ticket Id': 'CM-AL-3', 'Task Type': 'CM', 'Dispatch Time': inicio(300), 'SLA Hour': '240'}))]  # vencido
        db.session.add_all(filas); db.session.commit()
        ids = [f.id for f in filas]
    sla._CACHE_ALERTAS.clear()
    try:
        alertas = {a['ticket']: a for a in auth_client.get('/api/sla/alertas').json['alertas']}
        assert 'CM-AL-1' in alertas and 38 <= alertas['CM-AL-1']['resto'] <= 41 and alertas['CM-AL-1']['proyecto'] == 'Claro'
        assert 'CM-AL-2' not in alertas and 'CM-AL-3' not in alertas
    finally:
        sla._CACHE_ALERTAS.clear()
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False); db.session.commit()
