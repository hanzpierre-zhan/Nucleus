import io
import json

import pytest

from db import db
from models import Proyecto, NucleusData, RefacturableDetalle
from blueprints.cotizacion import _cot_en_proveedor


def test_items_importa_gasto_cobra_y_plantilla(auth_client):
    from openpyxl import load_workbook
    plantilla=auth_client.get('/api/cotizacion/items_template')
    assert plantilla.status_code==200
    wb=load_workbook(io.BytesIO(plantilla.data))
    assert any('GASTO COBRA' in str(v.formula1) for v in wb.active.data_validations.dataValidation)
    csv=b'TIPO,TEXTO EXPLICATIVO,UND,CANTIDAD,VALOR UNITARIO\nGASTO COBRA,Trabajo,Und,2,100\n'
    response=auth_client.post('/api/cotizacion/items_import',data={'file':(io.BytesIO(csv),'items.csv')})
    assert response.status_code==200,response.json
    assert response.json['items'][0]['tipo']=='GASTO COBRA'
    assert response.json['items'][0]['valor_total']=='200.0'

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
                           data_json=json.dumps({'ESTADO COTIZACION': 'En Aprobación', 'TIPO GASTO APROBACION':'Proveedor'}))
        db.session.add(fila)
        db.session.commit()
    yield pid, 'TEST-PROVEEDOR'
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value='TEST-PROVEEDOR').first()
        if fila:
            rendicion = Proyecto.query.filter_by(nombre='Rendicion').one()
            NucleusData.query.filter_by(proyecto_id=rendicion.id, key_value='COT-'+str(fila.id)).delete()
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


def test_aprobacion_guarda_el_nombre_original_del_correo(app, auth_client, cotizacion):
    """El enlace guarda un nombre técnico; la aprobación conserva además el
    nombre original del archivo para poder mostrarlo en Liquidaciones."""
    pid, key = cotizacion
    subida = auth_client.post('/api/cotizacion/subir_correo', data={
        'key': key, 'adjunto': (io.BytesIO(b'correo outlook'), 'RE Aprobacion cotizacion.msg'),
    })
    assert subida.status_code == 200, subida.json
    assert subida.json['nombre'] == 'RE Aprobacion cotizacion.msg'
    respuesta = auth_client.post('/api/cotizacion/accion', json={
        'key': key, 'accion': 'conformar_aprobacion',
        'adjunto_correo': subida.json['url'], 'nombre_correo': subida.json['nombre'],
    })
    assert respuesta.status_code == 200, respuesta.json
    with app.app_context():
        datos = json.loads(NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one().data_json)
        assert datos['ADJUNTO CORREO CLIENTE'] == subida.json['url']
        assert datos['NOMBRE CORREO CLIENTE'] == 'RE Aprobacion cotizacion.msg'


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


def test_liquidacion_visible_desde_creacion_y_conserva_caso(app, auth_client, cotizacion):
    pid, key = cotizacion
    def registros():
        return [r for r in auth_client.get('/liquidaciones/api/registros').json['registros'] if r['cotizacion']==key]
    # La cotización aparece en Liquidaciones desde que se crea, sin esperar aprobación.
    assert len(registros())==1
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


@pytest.mark.parametrize('tipo,esperado',[('Caja chica','Caja Chica'),('Proveedor','Proveedor')])
def test_tipo_gasto_en_aprobacion(auth_client,cotizacion,tipo,esperado):
    pid,key=cotizacion
    r=auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion','tipo_gasto_aprobacion':tipo})
    assert r.status_code==200
    assert r.json['newData']['TIPO GASTO APROBACION']==esperado
    registros=auth_client.get('/liquidaciones/api/registros').json['registros']
    assert next(fila for fila in registros if fila['cotizacion']==key)['tipo_gasto']==esperado


def test_tipo_gasto_aprobacion_invalido(auth_client,cotizacion):
    pid,key=cotizacion
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion','tipo_gasto_aprobacion':'Otro'}).status_code==400


@pytest.mark.parametrize('gasto', ['Gasto Cobra','Refacturable'])
@pytest.mark.parametrize('pago', ['Caja chica','Proveedor',''])
def test_proveedor_depende_del_pago_aprobado(app, auth_client, cotizacion, gasto, pago):
    pid,key=cotizacion
    with app.app_context():
        fila=NucleusData.query.filter_by(proyecto_id=pid,key_value=key).one()
        datos=json.loads(fila.data_json);datos['TIPO DE GASTO']=gasto
        datos['_PROVEEDOR_PARALELO']=True
        fila.data_json=json.dumps(datos);db.session.commit()
    respuesta=auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion','tipo_gasto_aprobacion':pago})
    assert respuesta.status_code==200
    datos=respuesta.json['newData']
    assert _cot_en_proveedor(datos)==(pago=='Proveedor')
    from services.dashboard_cotizaciones import _en_proveedor
    assert _en_proveedor(datos)==(pago=='Proveedor')
    if pago!='Proveedor':
        assert auth_client.post('/api/cotizacion/proveedor',json={'key':key}).status_code==409


def test_cambiar_tipo_gasto_mueve_entre_caja_chica_y_proveedor(app, auth_client, cotizacion):
    pid, key = cotizacion
    # Antes de aprobar (pestaña Cliente) no se puede mover.
    antes = auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'cambiar_tipo_gasto', 'tipo_gasto_aprobacion': 'Caja chica'})
    assert antes.status_code == 409
    # Aprobar: la cotización queda en Pdt. Sustento (aparece en Proveedor).
    aprobada = auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'conformar_aprobacion'})
    assert aprobada.status_code == 200
    assert _cot_en_proveedor(aprobada.json['newData'])
    # Mover a caja chica: sale de la pestaña Proveedor.
    a_caja = auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'cambiar_tipo_gasto', 'tipo_gasto_aprobacion': 'Caja chica'})
    assert a_caja.status_code == 200, a_caja.json
    datos = a_caja.json['newData']
    assert datos['TIPO GASTO APROBACION'] == 'Caja Chica'
    assert datos['_PROVEEDOR_PARALELO'] is False
    assert not _cot_en_proveedor(datos)
    assert datos['_TIPO_GASTO_MODIFICADO']['anterior'] == 'Proveedor'
    # Volver a proveedor: reaparece en la pestaña.
    a_prov = auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'cambiar_tipo_gasto', 'tipo_gasto_aprobacion': 'Proveedor'})
    assert a_prov.status_code == 200
    assert _cot_en_proveedor(a_prov.json['newData'])
    # Tipo de gasto inválido.
    assert auth_client.post('/api/cotizacion/accion', json={'key': key, 'accion': 'cambiar_tipo_gasto', 'tipo_gasto_aprobacion': 'Otro'}).status_code == 400
    # El cambio queda persistido en la fila.
    with app.app_context():
        guardado = json.loads(NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one().data_json)
        assert guardado['TIPO GASTO APROBACION'] == 'Proveedor'


def test_adjunto_cotizacion_con_clave_que_requiere_sanear(app, auth_client, cotizacion):
    pid, original = cotizacion
    clave = 'QA Cotización con espacios'
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value=original).one()
        fila.key_value = clave
        db.session.commit()
    try:
        with auth_client.session_transaction() as ses:
            ses.update(current_proyecto_id=pid, current_proyecto_nombre='Cotizaciones')
        contenido = b'%PDF-1.4 oferta'
        subida = auth_client.post('/api/cotizacion/subir_cotizacion_proveedor', data={
            'key': clave, 'adjunto': (io.BytesIO(contenido), 'oferta.pdf')})
        assert subida.status_code == 200, subida.json
        assert auth_client.get(subida.json['url']).data == contenido
    finally:
        with app.app_context():
            fila = NucleusData.query.filter_by(proyecto_id=pid, key_value=clave).one()
            fila.key_value = original
            db.session.commit()



def test_nombre_desde_subida_sin_depender_del_navegador(app,auth_client,cotizacion):
    pid,key=cotizacion
    original='RE Aprobación del cliente 2026.msg'
    subida=auth_client.post('/api/cotizacion/subir_correo',data={
        'key':key,'adjunto':(io.BytesIO(b'correo original'),original)})
    assert subida.status_code==200 and subida.json['nombre']==original
    with app.app_context():
        datos=json.loads(NucleusData.query.filter_by(proyecto_id=pid,key_value=key).one().data_json)
        assert original in datos['_ADJUNTOS_NOMBRES'].values()
    respuesta=auth_client.post('/api/cotizacion/accion',json={
        'key':key,'accion':'conformar_aprobacion','adjunto_correo':subida.json['url']})
    assert respuesta.status_code==200,respuesta.text
    assert respuesta.json['newData']['NOMBRE CORREO CLIENTE']==original
    descarga=auth_client.get(subida.json['url'])
    assert descarga.data==b'correo original'
    assert "filename*=UTF-8''RE%20Aprobaci%C3%B3n%20del%20cliente%202026.msg" in descarga.headers['Content-Disposition']
    auth_client.get('/switch_project/%s'%pid)
    html=auth_client.get('/').text
    assert 'Nombre del archivo del correo' in html
    assert 'Correo de aprobación' in html


def test_nombre_almacenado_prevalece_sobre_nombre_manipulado(auth_client,cotizacion):
    pid,key=cotizacion
    subida=auth_client.post('/api/cotizacion/subir_correo',data={
        'key':key,'adjunto':(io.BytesIO(b'correo'),'Aprobacion real.msg')})
    r=auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion',
        'adjunto_correo':subida.json['url'],'nombre_correo':'otro archivo.msg'})
    assert r.status_code==200
    assert r.json['newData']['NOMBRE CORREO CLIENTE']=='Aprobacion real.msg'


@pytest.mark.parametrize('rol',['zeno','gestor','supervisor'])
def test_envio_a_transito_vinculado_sin_duplicar(app,auth_client,cotizacion,rol):
    from models import Usuario,AccesoProyecto
    from services.rendicion_estados import etapa_de
    pid,key=cotizacion
    uid=None
    with app.app_context():
        origen=NucleusData.query.filter_by(proyecto_id=pid,key_value=key).one();origen_id=origen.id
        origen.data_json=json.dumps({'ESTADO COTIZACION':'Aprobado','CLIENTE':'ENTEL','TIPO GASTO APROBACION':'Proveedor',
            'MOTIVO':'Traslado de equipo','NOMBRE SITE':'Site de prueba','NUMERO WO':'WO-TEST','SUB TOTAL + FEE':'125.50','TIPO DE GASTO':'Refacturable'})
        rend=Proyecto.query.filter_by(nombre='Rendicion').one().id
        if rol!='zeno':
            u=Usuario(username='transito-'+rol,password_hash='no-login',rol=rol)
            db.session.add(u);db.session.flush();uid=u.id
            flm=Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
            for acceso in (pid,flm,rend):db.session.add(AccesoProyecto(usuario_id=uid,proyecto_id=acceso,restricciones='{}'))
        db.session.commit()
    if uid:
        with auth_client.session_transaction() as s:s.update(user_id=uid,username='transito-'+rol,rol=rol)
    try:
        payload={'key':key,'accion':'cambiar_tipo_gasto','tipo_gasto_aprobacion':'Caja chica'}
        for intento in range(2):
            r=auth_client.post('/api/cotizacion/accion',json=payload)
            assert r.status_code==200,r.text
        enlace=r.json['newData']['_RENDICION_TRANSITO']
        with app.app_context():
            q=NucleusData.query.filter_by(proyecto_id=rend,key_value=enlace['key'])
            assert q.count()==1
            traslado=q.one();datos=json.loads(traslado.data_json)
            assert etapa_de(datos)=='TRANSITO'
            assert datos['N° COTIZACION']==key and datos['Monto total del depósito']=='125.50'
            assert datos['Nombre del proyecto']=='ENTEL' and datos['Motivo de la solicitud']=='Traslado de equipo'
            assert datos['_COTIZACION_ORIGEN']['id']==origen_id
            # Un reintento no altera el trabajo realizado posteriormente en Rendición.
            datos.update(ESTADO='VALIDADO',OBSERVACIONES='Conservar');traslado.data_json=json.dumps(datos);db.session.commit()
        assert auth_client.post('/api/cotizacion/accion',json=payload).status_code==200
        with app.app_context():
            datos=json.loads(NucleusData.query.filter_by(proyecto_id=rend,key_value=enlace['key']).one().data_json)
            assert datos['ESTADO']=='VALIDADO' and datos['OBSERVACIONES']=='Conservar'
        auth_client.get('/switch_project/%s'%rend)
        html=auth_client.get('/').text
        assert 'rend-cnt-transito' in html
    finally:
        if uid:
            with app.app_context():
                AccesoProyecto.query.filter_by(usuario_id=uid).delete()
                db.session.delete(db.session.get(Usuario,uid));db.session.commit()
