import json
import pytest
from db import db
from models import Proyecto, NucleusData, RefacturableDetalle

@pytest.fixture
def liquidacion(app):
    with app.app_context():
        cot = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        flm = Proyecto.query.filter_by(nombre='FLM - CLARO').one()
        wo = NucleusData(proyecto_id=flm.id, key_value='LIQ-WO-TEST', data_json=json.dumps({'ESTADO DE EJECUCION':'Culminado','_EVIDENCIA_INICIO':json.dumps(['/static/inicio.jpg']),'_BITACORA_INICIO':'Trabajo iniciado'}))
        fila = NucleusData(proyecto_id=cot.id, key_value='LIQ-COT-TEST',data_json=json.dumps({'ESTADO COTIZACION':'Atendido','SOLICITADO POR':'solicitante','GESTOR':'otro','NUMERO WO':'LIQ-WO-TEST','SUB TOTAL + FEE':'210.00','SUBTOTAL FACTURA PROVEEDOR':'120.50','GENERADA':'1','FECHA INICIO OBRA':'2026-10-01','FECHA FIN OBRA':'2026-10-09','ADJUNTO FACTURA PROVEEDOR':'/api/cotizacion/correo/1/test/factura.pdf','ADJUNTO CORREO CLIENTE':'/api/cotizacion/correo/1/test/correo.msg'}))
        db.session.add_all([wo,fila]);db.session.commit();ids=(fila.id,wo.id)
    yield ids[0]
    with app.app_context():
        RefacturableDetalle.query.filter_by(origen_id=ids[0]).delete()
        NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()


def obtener(client, id):
    r=client.get('/liquidaciones/api/registros');assert r.status_code==200
    return next(row for row in r.json['registros'] if row['id']==id)


def test_liquidacion_fuentes_documentos_y_avance(app,auth_client,liquidacion):
    row=obtener(auth_client,liquidacion)
    assert row['gestor']=='solicitante'
    assert row['nombre_proyecto']=='CLARO'
    assert row['estatus']=='Culminado'
    assert row['fecha_inicio']=='2026-10-01' and row['fecha_fin']=='2026-10-09'
    assert row['monto_hw']=='210.00' and row['monto_factura_proveedor']=='120.50'
    assert row['avance']==100
    assert row['fotos']['inicio']==['/static/inicio.jpg']
    assert row['comentarios']['inicio']=='Trabajo iniciado'
    with app.app_context():
        fila=db.session.get(NucleusData,liquidacion);d=json.loads(fila.data_json);d.pop('ADJUNTO FACTURA PROVEEDOR');fila.data_json=json.dumps(d);db.session.commit()
    assert obtener(auth_client,liquidacion)['avance']==75
    r=auth_client.patch('/liquidaciones/api/registros/%s'%liquidacion,json={'no_aplica_factura':'1','codigo_ajb_ejb':'AJB-123','mes_cierre':'2026-10','estado_liquidacion':'En revisión'})
    assert r.status_code==200
    assert r.json['registro']['avance']==100
    assert r.json['registro']['documentos']['factura']=='No aplica'
    assert r.json['registro']['codigo_ajb_ejb']=='AJB-123'
    assert r.json['registro']['correlativo']==row['correlativo']

@pytest.mark.parametrize('cambios',[{'fecha_inicio':'2026-10-01'},{'fecha_fin':'2026-10-09'},{'estatus':'Culminado'},{'no_aplica_factura':'si'},{'estado_liquidacion':'inventado'},{'mes_cierre':'2026-13'}])
def test_liquidaciones_rechaza_edicion_derivada_o_invalida(auth_client,liquidacion,cambios):
    assert auth_client.patch('/liquidaciones/api/registros/%s'%liquidacion,json=cambios).status_code==400


def test_fechas_en_sustento_validacion_y_persistencia(app,auth_client,liquidacion):
    bad=auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'LIQ-COT-TEST','fecha_inicio':'2026-10-09','fecha_fin':'2026-10-01'})
    assert bad.status_code==400
    good=auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'LIQ-COT-TEST','fecha_inicio':'2026-10-02','fecha_fin':'2026-10-08','bitacoras':{'cierre':'Obra concluida'}})
    assert good.status_code==200,good.json
    row=obtener(auth_client,liquidacion)
    assert row['fecha_inicio']=='2026-10-02' and row['fecha_fin']=='2026-10-08'
    assert 'Obra concluida' in row['comentarios']['cierre']


def test_nombre_liquidaciones_y_compatibilidad(auth_client):
    for ruta in ('/liquidaciones/','/refacturable/'):
        r=auth_client.get(ruta);assert r.status_code==200
        assert b'Liquidaciones' in r.data and b'name="codigo_ajb_ejb"' in r.data


def test_descarga_cotizacion_generada(auth_client, liquidacion):
    response=auth_client.get('/liquidaciones/api/registros/%s/pdf'%liquidacion)
    assert response.status_code==200
    assert response.mimetype=='application/pdf'
    assert response.data.startswith(b'%PDF')


def test_resumen_conserva_importes_documentos_y_datos_manuales(auth_client, liquidacion):
    completo = obtener(auth_client, liquidacion)
    response = auth_client.get('/liquidaciones/api/registros?resumen=1')
    assert response.status_code == 200
    resumen = next(r for r in response.json['registros'] if r['id'] == liquidacion)
    assert resumen.pop('tiene_sustento') is True
    assert resumen == {k: v for k, v in completo.items() if k not in ('fotos', 'comentarios')}
    assert len(response.data) < len(auth_client.get('/liquidaciones/api/registros').data)


def test_sustento_bajo_demanda_lee_cambios_recientes(app, auth_client, liquidacion):
    ruta = f'/liquidaciones/api/registros/{liquidacion}/sustento'
    response = auth_client.get(ruta)
    assert response.status_code == 200
    assert response.json['registro']['fotos']['inicio'] == ['/static/inicio.jpg']
    with app.app_context():
        wo = NucleusData.query.filter_by(key_value='LIQ-WO-TEST').one()
        datos = json.loads(wo.data_json)
        datos['_BITACORA_INICIO'] = 'Actualizado después de abrir el listado'
        wo.data_json = json.dumps(datos)
        db.session.commit()
    assert auth_client.get(ruta).json['registro']['comentarios']['inicio'] == datos['_BITACORA_INICIO']
    assert auth_client.get('/liquidaciones/api/registros/999999999/sustento').status_code == 404


def test_listado_consultas_acotadas_y_fuentes_parseadas_una_vez(app, auth_client, liquidacion, monkeypatch):
    from sqlalchemy import event
    from blueprints.refacturable import _registros

    obtener(auth_client, liquidacion)  # La numeración histórica ya está asignada.
    with app.app_context():
        raw_wo = NucleusData.query.filter_by(key_value='LIQ-WO-TEST').one().data_json
        lecturas, consultas = [], []
        original = json.loads

        def leer(valor, *args, **kwargs):
            if valor == raw_wo:
                lecturas.append(valor)
            return original(valor, *args, **kwargs)

        def registrar(_conn, _cursor, statement, _params, _context, _many):
            consultas.append(statement)

        monkeypatch.setattr(json, 'loads', leer)
        event.listen(db.engine, 'before_cursor_execute', registrar)
        try:
            registros = _registros(origen_ids=[liquidacion])
        finally:
            event.remove(db.engine, 'before_cursor_execute', registrar)
        assert [r['id'] for r in registros] == [liquidacion]
        assert registros[0]['avance'] == 100
        assert len(consultas) == 2
        assert len(lecturas) == 1


def test_guardar_caso_no_procesa_seguimientos_ajenos(app, auth_client, liquidacion):
    with app.app_context():
        cot = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        ajeno = NucleusData(proyecto_id=cot.id, key_value='LIQ-AJENO-INVALIDO', data_json='{}')
        db.session.add(ajeno)
        db.session.flush()
        ajeno_id = ajeno.id
        db.session.add(RefacturableDetalle(origen_id=ajeno_id, data_json='{invalido'))
        db.session.commit()
    try:
        response = auth_client.patch(f'/liquidaciones/api/registros/{liquidacion}?resumen=1',
                                     json={'observacion': 'Guardado sin recorrer otros casos'})
        assert response.status_code == 200
        registro = response.json['registro']
        assert registro['observacion'] == 'Guardado sin recorrer otros casos'
        assert registro['tiene_sustento'] is True
        assert 'fotos' not in registro
    finally:
        with app.app_context():
            RefacturableDetalle.query.filter_by(origen_id=ajeno_id).delete()
            NucleusData.query.filter_by(id=ajeno_id).delete()
            db.session.commit()


def test_navegador_carga_ligera_sustento_y_recuperacion(app, auth_client, liquidacion):
    import threading
    from werkzeug.serving import make_server
    playwright = pytest.importorskip('playwright.sync_api')

    servidor = make_server('127.0.0.1', 0, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        with playwright.sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            try:
                contexto = navegador.new_context()
                contexto.add_cookies([{'name': 'session', 'value': auth_client.get_cookie('session').value,
                                       'domain': '127.0.0.1', 'path': '/'}])
                pagina = contexto.new_page()
                errores, consultas = [], []
                pagina.on('pageerror', lambda error: errores.append(str(error)))
                pagina.on('request', lambda req: consultas.append(req.url))
                pagina.goto(f'http://127.0.0.1:{servidor.server_port}/liquidaciones/',
                             wait_until='networkidle')
                fila = pagina.locator('#ref-grid .tabulator-row', has_text='LIQ-COT-TEST')
                playwright.expect(fila).to_be_visible()
                assert sum('/api/registros?resumen=1' in url for url in consultas) == 1
                assert not any('/sustento' in url or '/api/rendiciones' in url for url in consultas)

                patron = f'**/api/registros/{liquidacion}/sustento'
                pagina.route(patron, lambda route: route.fulfill(
                    status=503, content_type='application/json', body='{"error":"Sustento temporalmente no disponible"}'))
                fila.get_by_role('button', name='Ver sustento').click()
                playwright.expect(pagina.locator('#liq-sustento-body')).to_have_text('Sustento temporalmente no disponible')
                pagina.locator('#liq-sustento-close').click()
                pagina.unroute(patron)
                fila.get_by_role('button', name='Ver sustento').click()
                playwright.expect(pagina.locator('#liq-sustento-body')).to_contain_text('Trabajo iniciado')
                playwright.expect(pagina.locator('#liq-sustento-body img')).to_have_attribute('src', '/static/inicio.jpg')
                pagina.locator('#liq-sustento-close').click()

                fila.get_by_role('link', name='Datos manuales de la cotización LIQ-COT-TEST').click()
                pagina.locator('[name="observacion"]').fill('Edición desde carga ligera')
                pagina.locator('#ref-save').click()
                playwright.expect(pagina.locator('#ref-editor')).not_to_be_visible()
                playwright.expect(fila).to_contain_text('Edición desde carga ligera')
                assert errores == []
            finally:
                navegador.close()
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)
        servidor.server_close()
