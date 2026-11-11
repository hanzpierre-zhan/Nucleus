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


def test_nuevo_registro_busca_sites_y_wo_del_proyecto(app, auth_client):
    with app.app_context():
        site = Proyecto.query.filter_by(nombre='SITE').one().id
        flm = Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        filas = [NucleusData(proyecto_id=site, key_value='ZZ9901_PRUEBA', data_json=json.dumps({
                    'Site': 'ZZ9901_PRUEBA', 'Nombre del sitio | Site name': 'PRUEBA', 'Código del sitio | Site ID': 'ZZ9901',
                    'Distrito | District': 'PERENE', 'Provincia | Provincia': 'CHANCHAMAYO', 'Region | Region': 'CENTRO', 'Proyecto': 'FLM - CLARO'})),
                 NucleusData(proyecto_id=flm, key_value='CM-20261109-00009901', data_json=json.dumps({'Site ID': 'ZZ9901', 'Site Name': 'PRUEBA'}))]
        db.session.add_all(filas); db.session.commit()
        ids = [f.id for f in filas]
    try:
        sitios = auth_client.get('/api/cot-new/sites?proyecto=FLM - CLARO&q=ZZ9901').json['sites']
        assert sitios == [{'site': 'ZZ9901_PRUEBA', 'nombre': 'PRUEBA', 'codigo': 'ZZ9901', 'distrito': 'PERENE',
                           'provincia': 'CHANCHAMAYO', 'region': 'CENTRO'}]
        assert auth_client.get('/api/cot-new/sites?proyecto=FLM - ENTEL&q=ZZ9901').json['sites'] == []  # otro proyecto
        wos = auth_client.get('/api/cot-new/wos?proyecto=FLM - CLARO&codigo=ZZ9901&nombre=PRUEBA').json['wos']
        assert 'CM-20261109-00009901' in wos
        assert auth_client.get('/api/cot-new/sites?proyecto=OTRO').status_code == 400
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False); db.session.commit()


def test_flujo_pago_caja_chica_proveedor_transito(app, auth_client):
    from blueprints.cot_new import pestanas_de
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        base = {'CLIENTE': 'CLARO', 'ESTADO COTIZACION': 'Aprobado', '_PAGO_PENDIENTE': '1', 'SUB TOTAL + FEE': '100.00'}
        transito = NucleusData(proyecto_id=pid, key_value='CN-PAGO-T', data_json=json.dumps({**base, 'TIPO GASTO APROBACION': 'Tránsito', 'MONTO TRANSITO': '80.00'}))
        caja = NucleusData(proyecto_id=pid, key_value='CN-PAGO-C', data_json=json.dumps({**base, 'TIPO GASTO APROBACION': 'Caja Chica'}))
        db.session.add_all([transito, caja]); db.session.commit()
    pestanas = lambda key: next(c for c in auth_client.get('/api/cot-new/lista').json['cotizaciones'] if c['key'] == key)['pestanas']
    foto = '/api/cotizacion/correo/%d/%s/pago_abc.jpg'
    try:
        # Aprobadas antes del flujo de pago: van directo a Operaciones.
        assert pestanas_de({'ESTADO COTIZACION': 'Aprobado', 'TIPO GASTO APROBACION': 'Caja Chica'}) == ['sustentar']
        # Tránsito: cae en Caja chica; al pagar va a Operaciones y queda en Tránsito.
        assert pestanas('CN-PAGO-T') == ['cajachica']
        assert auth_client.post('/api/cot-new/pagar', json={'key': 'CN-PAGO-T', 'foto': '/otra/foto.jpg'}).status_code == 400
        r = auth_client.post('/api/cot-new/pagar', json={'key': 'CN-PAGO-T', 'foto': foto % (pid, 'CN-PAGO-T')})
        assert r.status_code == 200 and r.json['pestanas'] == ['sustentar', 'transito'], r.json
        fila = next(c for c in auth_client.get('/api/cot-new/lista').json['cotizaciones'] if c['key'] == 'CN-PAGO-T')
        # Tránsito paga el monto definido y deja la provisión (20 % de ese monto) para el proveedor.
        assert fila['FECHA PAGO'] and fila['FOTO PAGO'].endswith('pago_abc.jpg') and fila['MONTO PAGADO'] == '80.00'
        assert fila['PROVISION'] == '16.00'
        assert auth_client.post('/api/cot-new/pagar', json={'key': 'CN-PAGO-T', 'foto': foto % (pid, 'CN-PAGO-T')}).status_code == 409
        r = auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-T', 'desde': 'transito', 'hacia': 'proveedor'})
        assert r.json['pestanas'] == ['sustentar', 'proveedor']
        # En Proveedor (ya pagada): derivar a Caja chica la saca de Proveedor y sigue en Operaciones.
        r = auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-T', 'desde': 'proveedor', 'hacia': 'cajachica'})
        assert r.json['pestanas'] == ['sustentar']
        # Pasar a Tránsito exige el monto a depositar.
        assert auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-C', 'desde': 'cajachica', 'hacia': 'transito'}).status_code == 400
        r = auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-C', 'desde': 'cajachica', 'hacia': 'transito', 'monto_transito': '50'})
        assert r.status_code == 200 and r.json['pestanas'] == ['cajachica']
        fila = next(c for c in auth_client.get('/api/cot-new/lista').json['cotizaciones'] if c['key'] == 'CN-PAGO-C')
        assert fila['MONTO TRANSITO'] == '50.00'
        # Caja chica: a Proveedor (pide factura antes de pagar; en paralelo ya está en Operaciones) y de vuelta a Caja chica.
        assert auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-C', 'desde': 'cajachica', 'hacia': 'proveedor'}).json['pestanas'] == ['sustentar', 'proveedor']
        assert auth_client.post('/api/cot-new/pagar', json={'key': 'CN-PAGO-C', 'foto': foto % (pid, 'CN-PAGO-C')}).status_code == 409
        assert auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-C', 'desde': 'transito', 'hacia': 'proveedor'}).status_code == 409
        assert auth_client.post('/api/cot-new/mover', json={'key': 'CN-PAGO-C', 'desde': 'proveedor', 'hacia': 'cajachica'}).json['pestanas'] == ['cajachica']
        r = auth_client.post('/api/cot-new/pagar', json={'key': 'CN-PAGO-C', 'foto': foto % (pid, 'CN-PAGO-C')})
        assert r.json['pestanas'] == ['sustentar']
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.key_value.in_(['CN-PAGO-T', 'CN-PAGO-C'])).delete(); db.session.commit()


def test_estado_de_pago_y_operativo():
    from blueprints.cot_new import estado_operativo, estado_pago
    base = {'ESTADO COTIZACION': 'Aprobado'}
    assert estado_pago({'ESTADO COTIZACION': 'En Aprobación'}) == '' and estado_operativo({'ESTADO COTIZACION': 'En Aprobación'}) == ''
    assert estado_pago({**base, '_PAGO_PENDIENTE': '1', 'TIPO GASTO APROBACION': 'Caja Chica'}) == 'Pendiente Depósito'
    assert estado_pago({**base, 'TIPO GASTO APROBACION': 'Caja Chica', 'FECHA PAGO': 'x'}) == 'Depositado Caja Chica'
    assert estado_pago({**base, 'TIPO GASTO APROBACION': 'Tránsito', 'FECHA PAGO': 'x'}) == 'Depositado sin proveedor'
    factura = {'NUMERO FACTURA PROVEEDOR': 'F1', 'NUMERO OC PROVEEDOR': 'OC1', 'ADJUNTO FACTURA PROVEEDOR': '/f.pdf', 'SUBTOTAL FACTURA PROVEEDOR': '10'}
    assert estado_pago({**base, 'TIPO GASTO APROBACION': 'Tránsito', 'FECHA PAGO': 'x', **factura}) == 'Facturado Proveedor'
    assert estado_pago({**base, 'TIPO GASTO APROBACION': 'Proveedor', '_PAGO_PENDIENTE': '1'}) == 'Pendiente Depósito'
    # Operativo: por las fechas de la ficha (todas las WO) y Sustentado al pasar a Atendido.
    assert estado_operativo({**base, 'NUMERO WO': 'CM-1'}) == 'Pdt. ejecutar'
    assert estado_operativo({**base, 'NUMERO WO': 'CM-1', 'INICIO EJECUCION': '2026-11-10 08:00:00'}) == 'En ejecución'
    assert estado_operativo({**base, 'NUMERO WO': 'CM-1', 'INICIO EJECUCION': 'a', 'FIN EJECUCION': 'b'}) == 'Ejecutado en campo'
    dos = {**base, 'NUMERO WO': 'CM-1, CM-2', '_EJECUCION_WO': {'cm-1': {'inicio': 'a', 'fin': 'b'}}}
    assert estado_operativo(dos) == 'En ejecución'
    dos['_EJECUCION_WO']['cm-2'] = {'inicio': 'a', 'fin': 'b'}
    assert estado_operativo(dos) == 'Ejecutado en campo'
    assert estado_operativo({'ESTADO COTIZACION': 'Atendido'}) == 'Sustentado'


def test_eliminar_cotizaciones_marcadas(app, auth_client, cambiar_rol):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        db.session.add_all([NucleusData(proyecto_id=pid, key_value=k, data_json=json.dumps({'CLIENTE': 'CLARO'}))
                            for k in ('CN-DEL-1', 'CN-DEL-2')])
        db.session.commit()
    try:
        cambiar_rol(auth_client, 'zeno')
        assert 'id="cc-eliminar"' in auth_client.get('/cot-new/').get_data(as_text=True)
        cambiar_rol(auth_client, 'admin')
        assert 'id="cc-eliminar"' not in auth_client.get('/cot-new/').get_data(as_text=True)
        assert auth_client.post('/api/cot-new/eliminar', json={'keys': ['CN-DEL-1']}).status_code == 403
        cambiar_rol(auth_client, 'zeno')
        assert auth_client.post('/api/cot-new/eliminar', json={'keys': ['CN-DEL-1', 'CN-DEL-2']}).json == {'success': True}
        with app.app_context():
            assert not NucleusData.query.filter(NucleusData.key_value.in_(['CN-DEL-1', 'CN-DEL-2'])).count()
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.key_value.in_(['CN-DEL-1', 'CN-DEL-2'])).delete(); db.session.commit()


def test_depositos_de_caja_chica_por_cotizacion(app, auth_client):
    from models import CajaChicaSolicitud
    base = {'documento': '70000000', 'tecnico': 'Técnico', 'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '123456'}
    revision = lambda cot: json.dumps([{'revision': {'cotizacion': cot}}])
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        db.session.add_all([
            NucleusData(proyecto_id=pid, key_value='CN-DEP-1', data_json=json.dumps({'N° COTIZACION': 'COT-DEP-1', 'CLIENTE': 'CLARO'})),
            CajaChicaSolicitud(codigo='COB-90001', total=50, estado='DEPOSITADO', historial=revision('cot-dep-1'), **base),
            CajaChicaSolicitud(codigo='COB-90002', total=30, estado='VALIDADO', historial=revision('COT-DEP-1'), **base),
            CajaChicaSolicitud(codigo='COB-90003', total=99, estado='ANULADO', historial=revision('COT-DEP-1'), **base)])
        db.session.commit()
    try:
        fila = next(c for c in auth_client.get('/api/cot-new/lista').json['cotizaciones'] if c['key'] == 'CN-DEP-1')
        assert [(d['codigo'], d['monto'], d['estado'], d['tecnico']) for d in fila['depositos_cc']] == [
            ('COB-90001', '50.00', 'Depositada', 'Técnico'), ('COB-90002', '30.00', 'Validada', 'Técnico')]
        assert all(isinstance(d['id'], int) for d in fila['depositos_cc'])
    finally:
        with app.app_context():
            NucleusData.query.filter_by(key_value='CN-DEP-1').delete()
            CajaChicaSolicitud.query.filter(CajaChicaSolicitud.codigo.like('COB-9000%')).delete(synchronize_session=False)
            db.session.commit()
