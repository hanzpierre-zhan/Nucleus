import json
from db import db
from models import Proyecto, NucleusData


def test_cotizacion_viaja_cliente_sustento_proveedor_atendido(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        fila = NucleusData(proyecto_id=pid, key_value='AUDIT-FLUJO-COT', data_json=json.dumps({'ESTADO COTIZACION': 'Pdt. Cotización', 'SUB TOTAL + FEE': '100.00'}))
        db.session.add(fila);db.session.commit();origen_id=fila.id
    auth_client.get('/switch_project/%s' % pid)
    try:
        for accion, esperado in [('generar', 'En Aprobación'), ('conformar_aprobacion', 'Aprobado'), ('pasar_atendido', 'Atendido')]:
            resultado = auth_client.post('/api/cotizacion/accion', json={'key': 'AUDIT-FLUJO-COT', 'accion': accion})
            assert resultado.status_code == 200, resultado.json
            assert resultado.json['newData']['ESTADO COTIZACION'] == esperado
            if esperado != 'En Aprobación':
                assert resultado.json['newData']['_PROVEEDOR_PARALELO'] is True
                assert any(r['id'] == origen_id for r in auth_client.get('/refacturable/api/registros').json['registros'])
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=origen_id).delete();db.session.commit()


def test_rendicion_viaja_validacion_deposito_evidencia_cierre(app, auth_client, monkeypatch):
    import blueprints.rendicion as modulo
    monkeypatch.setattr(modulo, '_avisar_flujo', lambda *args: None)
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Rendicion').one().id
        fila = NucleusData(proyecto_id=pid, key_value='AUDIT-FLUJO-REND', data_json=json.dumps({'ESTADO': 'PENDIENTE', 'TIPO DE PRESUPUESTO': 'NO REFACTURABLE'}))
        db.session.add(fila);db.session.commit();origen_id=fila.id
    auth_client.get('/switch_project/%s' % pid)
    try:
        pasos = [
            ('validar', {'tiempo': 'Menor a 4 horas'}, 'VALIDADO'),
            ('depositar', {'fecha_pago': '2026-10-09', 'monto_pago': '100', 'foto_pago': '/static/audit-pago.jpg'}, 'DEPOSITADO'),
            ('sustentar', {'comentario': 'Sustento completado'}, 'SUSTENTADO'),
        ]
        for accion, campos, esperado in pasos:
            resultado = auth_client.post('/api/rendicion/accion', json={'key': 'AUDIT-FLUJO-REND', 'accion': accion, **campos})
            assert resultado.status_code == 200, resultado.json
            assert resultado.json['newData']['ESTADO'] == esperado
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=origen_id).delete();db.session.commit()
