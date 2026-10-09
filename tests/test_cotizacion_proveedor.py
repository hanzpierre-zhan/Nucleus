import io
import json

import pytest

from db import db
from models import Proyecto, NucleusData, RefacturableDetalle
from blueprints.cotizacion import _cot_en_proveedor

def test_aviso_cambio_estado_y_lectura(app, auth_client, cotizacion):
    from models import Notificacion
    pid, key = cotizacion
    auth_client.get('/switch_project/%s' % pid)
    respuesta = auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'conformar_aprobacion'})
    assert respuesta.status_code == 200, respuesta.json
    with app.app_context():
        aviso = Notificacion.query.filter_by(proyecto_id=pid, tipo='cotizacion_estado').order_by(Notificacion.id.desc()).first()
        assert aviso is not None
        assert key in aviso.texto and 'En Aprobación a Aprobado' in aviso.texto
        aviso_id = aviso.id
    listado = auth_client.get('/api/cotizacion/avisos')
    assert listado.status_code == 200
    assert any(a['id'] == aviso_id and not a['leida'] for a in listado.json['avisos'])
    assert auth_client.post('/api/cotizacion/avisos/leer', json={'ids': [aviso_id]}).status_code == 200
    assert any(a['id'] == aviso_id and a['leida'] for a in auth_client.get('/api/cotizacion/avisos').json['avisos'])
    auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'conformar_aprobacion'})
    with app.app_context():
        assert Notificacion.query.filter_by(proyecto_id=pid, tipo='cotizacion_estado').filter(Notificacion.texto.contains(key)).count() == 1


@pytest.fixture
def cotizacion(app, monkeypatch, tmp_path):
    import blueprints.cotizacion as modulo
    monkeypatch.setattr(modulo, '_cot_folder', lambda pid, key: str(tmp_path))
    monkeypatch.setattr(modulo, 'evidencia_usa_b2', lambda: False)
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        fila = NucleusData(proyecto_id=pid, key_value='TEST-PROVEEDOR',
                           data_json=json.dumps({'ESTADO COTIZACION': 'En Aprobación'}))
        db.session.add(fila)
        db.session.commit()
    yield pid, 'TEST-PROVEEDOR'
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value='TEST-PROVEEDOR').first()
        if fila:
            RefacturableDetalle.query.filter_by(origen_id=fila.id).delete()
        NucleusData.query.filter_by(proyecto_id=pid, key_value='TEST-PROVEEDOR').delete()
        db.session.commit()


def test_aprobar_con_proveedor_y_pdf(app, auth_client, cotizacion):
    pid, key = cotizacion
    contenido = b'%PDF-1.4\nProveedor test'
    subida = auth_client.post('/api/cotizacion/subir_cotizacion_proveedor', data={
        'key': key, 'adjunto': (io.BytesIO(contenido), 'oferta.pdf'),
    })
    assert subida.status_code == 200, subida.json
    url = subida.json['url']
    assert auth_client.get(url).data == contenido
    respuesta = auth_client.post('/api/cotizacion/accion', json={
        'key': key, 'accion': 'conformar_aprobacion',
        'nombre_proveedor': 'Proveedor SAC', 'adjunto_cotizacion_proveedor': url,
    })
    assert respuesta.status_code == 200, respuesta.json
    with app.app_context():
        datos = json.loads(NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one().data_json)
        assert datos['NOMBRE DE PROVEEDOR'] == 'Proveedor SAC'
        assert datos['ADJUNTO COTIZACION PROVEEDOR'] == url
        assert datos['ESTADO COTIZACION'] == 'Aprobado'


def test_pantalla_cotizaciones_carga_modal(auth_client, cotizacion):
    pid, _ = cotizacion
    auth_client.get('/switch_project/%d' % pid)
    respuesta = auth_client.get('/')
    assert respuesta.status_code == 200
    assert b'class="mar-modal cot-dialog"' in respuesta.data
    assert b'id="cot-provider-heading"' in respuesta.data
    assert b'id="cot-proveedor-archivo"' in respuesta.data
    assert b'id="cot-cnt-proveedor"' in respuesta.data
    assert b'id="cot-factura-numero"' in respuesta.data
    assert b'id="cot-oc-numero"' in respuesta.data


def test_rechaza_archivo_ejecutable(auth_client, cotizacion):
    _, key = cotizacion
    respuesta = auth_client.post('/api/cotizacion/subir_cotizacion_proveedor', data={
        'key': key, 'adjunto': (io.BytesIO(b'alert(1)'), 'oferta.html'),
    })
    assert respuesta.status_code == 400


def test_no_acepta_enlace_externo(auth_client, cotizacion):
    _, key = cotizacion
    respuesta = auth_client.post('/api/cotizacion/accion', json={
        'key': key, 'accion': 'conformar_aprobacion',
        'adjunto_cotizacion_proveedor': 'javascript:alert(1)',
    })
    assert respuesta.status_code == 400


def test_subida_requiere_cotizacion_existente(auth_client, cotizacion):
    respuesta = auth_client.post('/api/cotizacion/subir_cotizacion_proveedor', data={
        'key': 'NO-EXISTE', 'adjunto': (io.BytesIO(b'%PDF'), 'oferta.pdf'),
    })
    assert respuesta.status_code == 404


def test_proveedor_paralelo_no_cambia_sustento(app, auth_client, cotizacion):
    pid, key = cotizacion
    aprobacion = auth_client.post('/api/cotizacion/accion', json={
        'key': key, 'accion': 'conformar_aprobacion',
    })
    assert aprobacion.status_code == 200
    assert aprobacion.json['pestania'] == 'sustentar'
    assert _cot_en_proveedor(aprobacion.json['newData'])
    factura = auth_client.post('/api/cotizacion/subir_factura_proveedor', data={
        'key': key, 'adjunto': (io.BytesIO(b'%PDF-1.4\nFactura'), 'factura.pdf'),
    })
    assert factura.status_code == 200
    assert auth_client.get(factura.json['url']).status_code == 200
    guardado = auth_client.post('/api/cotizacion/proveedor', json={
        'key': key, 'numero_factura': 'F001-123', 'numero_oc': 'OC-456', 'subtotal_factura': '90.25',
        'factura_proveedor': factura.json['url'],
    })
    assert guardado.status_code == 200
    assert guardado.json['newData']['ESTADO COTIZACION'] == 'Aprobado'
    assert guardado.json['newData']['NUMERO FACTURA PROVEEDOR'] == 'F001-123'
    assert guardado.json['newData']['NUMERO OC PROVEEDOR'] == 'OC-456'
    assert guardado.json['newData']['SUBTOTAL FACTURA PROVEEDOR'] == '90.25'
    atendido = auth_client.post('/api/cotizacion/accion', json={
        'key': key, 'accion': 'pasar_atendido',
    })
    assert atendido.status_code == 200
    assert _cot_en_proveedor(atendido.json['newData'])
    assert atendido.json['newData']['ADJUNTO FACTURA PROVEEDOR'] == factura.json['url']
    with app.app_context():
        assert NucleusData.query.filter_by(proyecto_id=pid, key_value=key).count() == 1


def test_factura_no_se_guarda_antes_de_aprobar(auth_client, cotizacion):
    _, key = cotizacion
    respuesta = auth_client.post('/api/cotizacion/proveedor', json={
        'key': key, 'numero_factura': 'F-1', 'numero_oc': 'OC-1', 'subtotal_factura': '100',
        'factura_proveedor': '/archivo.pdf',
    })
    assert respuesta.status_code == 409


def test_proveedor_exige_los_tres_datos(auth_client, cotizacion):
    _, key = cotizacion
    auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'aprobar'})
    assert auth_client.post('/api/cotizacion/proveedor', json={
        'key': key, 'numero_factura': 'F-1', 'numero_oc': 'OC-1', 'subtotal_factura': '100',
    }).status_code == 400


def test_proveedor_rechaza_factura_de_otro_registro(auth_client, cotizacion):
    pid, key = cotizacion
    auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'aprobar'})
    respuesta = auth_client.post('/api/cotizacion/proveedor', json={
        'key': key, 'numero_factura': 'F-1', 'numero_oc': 'OC-1', 'subtotal_factura': '100',
        'factura_proveedor': '/api/cotizacion/correo/%d/OTRA/factura_proveedor_test.pdf' % pid,
    })
    assert respuesta.status_code == 400


def test_aprobacion_gatilla_liquidacion_y_conserva_caso(app, auth_client, cotizacion):
    pid, key = cotizacion
    def registros():
        return [r for r in auth_client.get('/liquidaciones/api/registros').json['registros'] if r['cotizacion']==key]
    assert registros()==[]
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion'}).status_code==200
    assert len(registros())==1
    origen_id=registros()[0]['id']
    with app.app_context():
        detalle=db.session.get(RefacturableDetalle,origen_id)
        assert detalle is not None
        assert json.loads(detalle.data_json)['estado_liquidacion']=='Pendiente'
    assert auth_client.patch('/liquidaciones/api/registros/%s'%origen_id,json={'observacion':'Caso en seguimiento'}).status_code==200
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'revertir'}).status_code==200
    assert len(registros())==1
    assert registros()[0]['estado_cotizacion']=='En Aprobación'
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion'}).status_code==200
    assert len(registros())==1 and registros()[0]['observacion']=='Caso en seguimiento'
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'revertir'}).status_code==200
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'cancelar','motivo':'Caso cancelado'}).status_code==200
    assert len(registros())==1 and registros()[0]['estado_cotizacion']=='Cancelado'
