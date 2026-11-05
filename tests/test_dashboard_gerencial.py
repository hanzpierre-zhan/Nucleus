import json
from datetime import datetime

from db import db
from models import AccesoProyecto, NucleusData, Proyecto, RefacturableDetalle
from services.dashboard_gerencial import resumen


def test_analytics_abre_gerencial(auth_client):
    response = auth_client.get('/analytics', follow_redirects=True)
    assert response.request.path == '/analytics/gerencial'
    assert 'Total depositado' in response.text
    assert 'Falta rendir' in response.text
    assert 'Evolución de depósitos' in response.text
    assert 'Alertas para tomar acción' in response.text
    assert 'Operación por proyecto' in response.text


def test_gerencial_cruza_carteras_y_respeta_restricciones(app, auth_client):
    with auth_client.session_transaction() as session:
        usuario = session['user_id']
    with app.app_context():
        proyectos = Proyecto.query.filter(Proyecto.nombre.in_(['FLM - ENTEL', 'Rendicion', 'Cotizaciones'])).all()
        ids = {p.nombre: p.id for p in proyectos}
        rows = [
            ('FLM - ENTEL', 'GER-LIMA', {'Departamento': 'LIMA', 'Operate Phase': 'dispatch', 'FECHA CREACION': '2026-10-01'}),
            ('FLM - ENTEL', 'GER-ICA', {'Departamento': 'ICA', 'Operate Phase': 'dispatch', 'FECHA CREACION': '2026-10-02'}),
            ('Rendicion', 'GER-DEP', {'ESTADO': 'DEPOSITADO', 'FECHA PAGO': '2026-10-10 11:00:00',
                                      'MONTO PAGO': '80.00', 'Nombre del proyecto': 'FLM - ENTEL',
                                      'Tipo de presupuesto': 'REFACTURABLE', 'N° COTIZACION': 'GER-COBRA'}),
            ('Cotizaciones', 'GER-COBRA', {'ESTADO COTIZACION': 'Aprobado', 'SUB TOTAL + FEE': '400', 'CLIENTE': 'ENTEL'}),
            ('Cotizaciones', 'GER-EST', {'ESTADO COTIZACION': 'Aprobado', 'SUB TOTAL + FEE': '110', 'CLIENTE': 'ENTEL',
                                        'TIPO DE GASTO': 'REFACTURABLE', 'TIPO GASTO APROBACION': 'Proveedor',
                                        'SUBTOTAL FACTURA PROVEEDOR': '100'}),
            ('Cotizaciones', 'GER-APR', {'ESTADO COTIZACION': 'Cotizado', 'SUB TOTAL + FEE': '70', 'CLIENTE': 'ENTEL'}),
        ]
        for nombre, key, data in rows:
            db.session.add(NucleusData(proyecto_id=ids[nombre], key_value=key, data_json=json.dumps(data)))
        origen = NucleusData.query.filter_by(key_value='GER-COBRA').one()
        detalle = RefacturableDetalle(origen_id=origen.id, data_json=json.dumps({
            'monto_cobra': '520', 'estado_liquidacion': 'Observado',
        }))
        db.session.add(detalle)
        acceso = AccesoProyecto.query.filter_by(usuario_id=usuario, proyecto_id=ids['FLM - ENTEL']).first()
        nuevo = acceso is None
        if nuevo:
            acceso = AccesoProyecto(usuario_id=usuario, proyecto_id=ids['FLM - ENTEL'])
            db.session.add(acceso)
        anterior = acceso.restricciones
        acceso.restricciones = json.dumps({'Departamento': ['LIMA']})
        db.session.commit()
        try:
            ahora = datetime(2026, 10, 13, 12)
            completo = resumen(proyectos, usuario, 'zeno', ahora)
            limitado = resumen([p for p in proyectos if p.nombre == 'FLM - ENTEL'], usuario, 'supervisor', ahora)
            assert completo['operaciones'][0]['antiguas'] >= 2
            assert any(a['titulo'] == 'Depósitos con más de 24 h sin sustento' and a['monto'] >= 80
                       for a in completo['alertas'])
            assert limitado['operaciones'][0]['antiguas'] < completo['operaciones'][0]['antiguas']
            assert all(a['url'] != '/analytics/rendicion' for a in limitado['alertas'])
            importes = completo['finanzas']['ENTEL']
            assert importes['por_cobrar_registrado'] == 520
            assert importes['estimado'] == 110
            assert importes['en_aprobacion'] == 70
            assert importes['sin_sustento'] == 80
            assert importes['sin_sustento_vencido'] == 80
            assert completo['depositos']['Refacturable']['por_rendir'] == 80
            assert completo['depositos_por_fecha']['2026-10-10']['Refacturable'] == 80
            assert completo['refacturables_caja'][0]['cotizacion'] == 'GER-COBRA'
            assert completo['refacturables_proveedor'][0]['monto'] == 100
            montos_entel = [a['monto'] for a in completo['impactos'] if a['grupo'] == 'ENTEL']
            assert montos_entel[0] == 520
            assert montos_entel == sorted(montos_entel, reverse=True)
            assert not limitado['finanzas']
        finally:
            db.session.delete(detalle)
            db.session.flush()
            NucleusData.query.filter(NucleusData.key_value.in_([key for _, key, _ in rows])).delete(synchronize_session=False)
            if nuevo:
                db.session.delete(acceso)
            else:
                acceso.restricciones = anterior
            db.session.commit()
