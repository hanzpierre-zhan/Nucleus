import io
import json

from openpyxl import load_workbook

from db import db
from models import NucleusData, Proyecto
from blueprints.cot_new import en_proveedor, pestana_de


def test_pestanas_segun_estado():
    assert pestana_de({'ESTADO COTIZACION': 'Pdt. Cotización'}) == 'registro'
    assert pestana_de({'ESTADO COTIZACION': 'En Aprobación'}) == 'cliente'
    assert pestana_de({'ESTADO COTIZACION': 'Aprobado'}) == 'sustentar'
    assert pestana_de({'ESTADO COTIZACION': 'Validado'}) == 'atendido'
    assert pestana_de({'ESTADO COTIZACION': 'Anulada'}) == 'cancelado'
    assert pestana_de({}) == 'registro'
    pendiente = {'ESTADO COTIZACION': 'Aprobado', 'TIPO GASTO APROBACION': 'Proveedor'}
    assert en_proveedor(pendiente)
    completo = {**pendiente, 'NUMERO FACTURA PROVEEDOR': 'F1', 'NUMERO OC PROVEEDOR': 'OC1',
                'ADJUNTO FACTURA PROVEEDOR': '/x.pdf', 'SUBTOTAL FACTURA PROVEEDOR': '10'}
    assert not en_proveedor(completo)
    assert not en_proveedor({'ESTADO COTIZACION': 'En Aprobación', 'TIPO GASTO APROBACION': 'Proveedor'})


def test_lista_y_exportar(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        fila = NucleusData(proyecto_id=pid, key_value='CN-TEST-1', data_json=json.dumps({
            'N° COTIZACION': 'CL-2026-11-999001', 'CLIENTE': 'CLARO', 'ESTADO COTIZACION': 'Aprobado',
            'TIPO GASTO APROBACION': 'Proveedor', 'SUB TOTAL + FEE': '2440.94',
            'ITEMS_JSON': json.dumps([{'texto': 'Cable', 'cantidad': '70', 'valor_unitario': '33.21', 'valor_total': '2440.94'}])}))
        db.session.add(fila); db.session.commit()
        fid = fila.id
    try:
        assert auth_client.get('/cot-new/').status_code == 200
        datos = next(c for c in auth_client.get('/api/cot-new/lista').json['cotizaciones'] if c['id'] == fid)
        assert datos['pestanas'] == ['sustentar', 'proveedor'] and datos['monto'] == '2440.94'
        assert datos['familia'] == 'CLARO' and datos['items'][0]['texto'] == 'Cable'
        r = auth_client.post('/api/cot-new/exportar', json=[fid])
        hoja = load_workbook(io.BytesIO(r.data)).active
        fila_excel = dict(zip([c.value for c in hoja[1]], [c.value for c in hoja[2]]))
        assert fila_excel['N° COTIZACION'] == 'CL-2026-11-999001' and fila_excel['Sub total + FEE'] == 2440.94
        assert auth_client.post('/api/cot-new/exportar', json='x').status_code == 400
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=fid).delete(); db.session.commit()


def test_nueva_cotizacion_desde_cot_new(app, auth_client):
    items = [{'tipo': 'REEMBOLSABLE', 'texto': 'Cable', 'cantidad': '10', 'valor_unitario': '33.21', 'valor_total': '348.71'}]
    r = auth_client.post('/api/cot-new/agregar', json={'key': '', 'numeracion_modo': 'automatico', 'data': {
        'CLIENTE': 'CLARO', 'MOTIVO': 'Prueba', 'ITEMS_JSON': json.dumps(items), 'SUB TOTAL + FEE': '348.71',
        'ESTADO COTIZACION': 'Pdt. Cotización'}})
    assert r.status_code == 200 and r.json['key'].startswith('CL-'), r.json
    try:
        fila = next(c for c in auth_client.get('/api/cot-new/lista').json['cotizaciones'] if c['key'] == r.json['key'])
        assert fila['pestanas'] == ['registro'] and fila['monto'] == '348.71' and fila['GESTOR']
    finally:
        with app.app_context():
            NucleusData.query.filter_by(key_value=r.json['key']).delete(); db.session.commit()
