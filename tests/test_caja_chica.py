"""Caja Chica: flujo completo con revisión por ítem, aislado de Rendición."""
import io
import json
import re

import pytest
from PIL import Image
from openpyxl import load_workbook

from db import db
from models import AppConfig, CajaChicaSolicitud, ClaveTecnico, NucleusData, Proyecto

DOC = '44445555'


@pytest.fixture
def tecnico(app, monkeypatch, tmp_path):
    from werkzeug.security import generate_password_hash
    monkeypatch.setitem(app.config, 'EVIDENCIA_DIR', str(tmp_path))
    monkeypatch.setitem(app.config, 'FORM_PRUEBAS_DIR', str(tmp_path / 'formularios'))
    monkeypatch.setitem(app.config, 'FORM_PRUEBAS_ENABLED', True)
    for clave in ('B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY'):
        monkeypatch.setitem(app.config, clave, '')
    monkeypatch.delenv('RENDER', raising=False)
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        fila = NucleusData(proyecto_id=pid, key_value=DOC, data_json=json.dumps(
            {'DOCUMENTO': DOC, 'TECNICO': 'Técnico Caja', 'ESTADO': 'ACTIVO', 'PROYECTO': 'FLM - CLARO',
             'SUPERVISOR': 'Supervisor Caja', 'DEPARTAMENTO': 'Junín'}))
        db.session.add_all([fila, ClaveTecnico(documento=DOC, clave_hash=generate_password_hash('Clave-123'))])
        db.session.commit()
        rid = fila.id
    cliente = app.test_client()
    pagina = cliente.get('/form-pruebas/')
    token = re.search(rb'id="csrf" type="hidden" value="([^"]+)"', pagina.data).group(1).decode()
    assert cliente.post('/form-pruebas/ingresar', json={'documento': DOC, 'clave': 'Clave-123'},
                        headers={'X-CSRF-Token': token}).json['debe_cambiar'] is False
    with cliente.session_transaction() as s:  # el ingreso renueva el token
        token = s['form_csrf']
    yield cliente, {'X-CSRF-Token': token}
    with app.app_context():
        CajaChicaSolicitud.query.filter_by(documento=DOC).delete()
        db.session.execute(db.text('DELETE FROM caja_chica_items WHERE solicitud_id NOT IN (SELECT id FROM caja_chica_solicitudes)'))
        NucleusData.query.filter_by(id=rid).delete()
        ClaveTecnico.query.filter_by(documento=DOC).delete()
        db.session.commit()


def foto(nombre='f.png'):
    b = io.BytesIO(); Image.new('RGB', (20, 20), 'blue').save(b, 'PNG'); b.seek(0)
    return (b, nombre)


def test_catalogo_aplica_por_proyecto_y_conserva_regla_de_solicitud(app, auth_client, tecnico):
    cli, headers = tecnico
    ruta = '/caja-chica/catalogo'
    pagina = auth_client.get(ruta)
    assert pagina.status_code == 200
    assert cli.get(ruta).status_code in (302, 401, 403)
    token = re.search(rb'data-csrf="([^"]+)"', pagina.data).group(1).decode()
    permisos = {'X-CSRF-Token': token}
    base = '/form-pruebas/caja-chica'
    catalogo = cli.get(base + '/datos').json['catalogo']
    materiales = next(c for c in catalogo if 'repuestos' in c['nombre'])
    assert materiales['proyectos']['PEXT'] == ''
    assert materiales['proyectos']['ENTEL'] == 'Refacturable'
    materiales['correo'] = True
    materiales['cotizacion'] = True
    assert auth_client.post(ruta, json=catalogo).status_code == 403
    try:
        assert auth_client.post(ruta, json=catalogo, headers=permisos).status_code == 200
        item = {'tipo_gasto': materiales['nombre'], 'monto': '50'}
        datos = {'proyecto': 'PEXT', 'motivo': 'Correctivo', 'banco': 'BCP', 'cuenta': '00123456789012345678', 'items': [item],
                 'site': 'LA2859', 'wo': 'CM-20260904-00000410', 'titular': 'Técnico Caja',
                 'tipo_billetera': 'Yape', 'numero_billetera': '900000000'}
        datos['proyecto'] = 'CLARO'
        # El técnico no da el correo: el concepto lo pide, pero lo adjunta la gestora al validar.
        respuesta = cli.post(base + '/solicitar', headers=headers, json=datos)
        assert respuesta.status_code == 200, respuesta.json
        materiales['proyectos']['CLARO'] = 'Refacturable'
        assert auth_client.post(ruta, json=catalogo, headers=permisos).status_code == 200
        guardado = cli.get(base + '/datos').json['solicitudes'][0]['items'][0]
        assert guardado['tipo_presupuesto'] == 'Gasto Cobra'
        assert guardado['correo_validador'] == '' and guardado['requiere_correo'] is True
        assert guardado['requiere_cotizacion'] is True
        sid = respuesta.json['solicitud']['id']
        gestion = f'/api/caja-chica/{sid}'
        assert auth_client.post(gestion + '/validar').status_code == 400
        datos['cotizacion'] = 'COT-001'
        datos['motivo'] = 'Correctivo revisado'
        correo = b'From: valida@example.com\r\nSubject: Aprobado\r\n\r\nConforme'
        revision = auth_client.post(gestion + '/editar', headers=permisos,
                                    data={'datos': json.dumps(datos), 'correo': (io.BytesIO(correo), 'aprobacion.eml')})
        assert revision.status_code == 200, revision.json
        assert revision.json['solicitud']['motivo'] == 'Correctivo revisado'
        assert revision.json['solicitud']['envio_tecnico']['motivo'] == 'Correctivo'
        assert revision.json['solicitud']['envio_tecnico']['formulario']['site'] == 'LA2859'
        assert revision.json['solicitud']['formulario']['numero_billetera'] == '900000000'
        assert revision.json['solicitud']['revision']['cotizacion'] == 'COT-001'
        assert auth_client.get(gestion + '/correo-validacion').data == correo
        documentos = auth_client.post(gestion + '/documentos', headers=permisos,
                                       data={'cotizacion': 'COT-002'})
        assert documentos.status_code == 200, documentos.json
        actualizada = documentos.json['solicitud']
        assert actualizada['revision']['cotizacion'] == 'COT-002'
        assert actualizada['motivo'] == 'Correctivo revisado'
        assert auth_client.get(gestion + '/correo-validacion').data == correo
        assert 'revision' not in cli.get(base + '/datos').json['solicitudes'][0]
        assert auth_client.post(gestion + '/validar').status_code == 200
    finally:
        with app.app_context():
            modulo = Proyecto.query.filter_by(nombre='Caja Chica').one()
            AppConfig.query.filter_by(proyecto_id=modulo.id, clave='catalogo_gastos').delete()
            db.session.commit()


def test_flujo_completo_con_item_rechazado_y_devolucion(app, auth_client, tecnico):
    cli, h = tecnico
    assert cli.get('/form-pruebas/caja-chica').status_code == 200
    r = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'Correctivo LA2859', 'banco': 'BCP', 'cuenta': '00123456789012345678', 'site': 'LA2859', 'wo': 'CM-20260904-00000410',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}, {'tipo_gasto': 'Peajes', 'descripcion': 'vuelta', 'monto': '50.00'}]})
    assert r.status_code == 200, r.json
    sol = r.json['solicitud']; sid = sol['id']
    assert re.fullmatch(r'COB-\d{5,}', sol['codigo'])
    assert int(sol['codigo'].split('-')[1]) >= 3000
    assert sol['total'] == '100.00' and sol['etapas'] == ['validacion']
    assert cli.get('/caja-chica/').status_code in (302, 401)  # el técnico no entra a la gestión

    def gestion(accion, **cuerpo):
        return auth_client.post('/api/caja-chica/%d/%s' % (sid, accion), json=cuerpo)
    assert auth_client.get('/caja-chica/').status_code == 200
    with auth_client.session_transaction() as sesion:
        token = sesion['form_csrf']
    exportacion = auth_client.post('/api/caja-chica/exportar', json=[sid], headers={'X-CSRF-Token': token})
    assert exportacion.status_code == 200
    libro = load_workbook(io.BytesIO(exportacion.data))
    hoja = libro['Historial']
    assert hoja['A2'].value == sol['codigo'] and hoja.max_row == 3  # una fila por ítem
    fila = dict(zip([c.value for c in hoja[1]], [c.value for c in hoja[2]]))
    assert [fila['Solicitado'], fila['Depositado'], fila['Estado de rendición'], fila['Estado de solicitud']] == [50, 0, 'Sin depósito', 'Validación']
    assert fila['Tipo de gasto'] == sol['items'][0].get('tipo_presupuesto', fila['Tipo de gasto'])
    assert fila['Supervisor'] == 'Supervisor Caja' and fila['Registrado en Dataper'] == 'Registrado'
    assert fila['Departamento (Dataper)'] == 'Junín'
    assert fila['Justificación'] == 'Correctivo LA2859'
    listado = next(x for x in auth_client.get('/api/caja-chica/solicitudes').json['solicitudes'] if x['id'] == sid)
    assert listado['dataper'] is True and listado['supervisor'] == 'Supervisor Caja'
    assert cli.get('/form-pruebas/caja-chica/datos', headers=h).json['cuenta_devolucion']['numero'] == '988191318'
    assert gestion('validar').status_code == 200
    # Depósito: monto exacto y foto
    r = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '90', 'foto': foto()})
    assert r.status_code == 400 and '100.00' in r.json['error']
    # La fecha y hora se registran solas; una fecha enviada se ignora.
    from datetime import datetime
    antes = datetime.utcnow().replace(second=0, microsecond=0)
    r = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'fecha': '2020-01-01', 'monto': '100', 'foto': foto()})
    assert r.status_code == 200 and r.json['solicitud']['etapas'] == ['por_rendir'], r.json
    assert datetime.fromisoformat(r.json['solicitud']['depositado_en']) >= antes
    assert r.json['solicitud']['deposito_fecha'] != '2020-01-01'
    items = r.json['solicitud']['items']

    def rendir(item, gastado):
        return cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h,
                        data={'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': gastado, 'fotos': [foto()],
                              'evidencia': foto('uso.png'), 'razon_social': 'FERRETERIA EL PERNO SAC'})
    assert rendir(items[0], '60').status_code == 400  # más que el ítem
    sin_evidencia = cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, items[0]['id']), headers=h,
                             data={'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': '50', 'fotos': [foto()]})
    assert sin_evidencia.status_code == 400 and 'evidencia' in sin_evidencia.json['error']
    assert rendir(items[0], '50').status_code == 200
    r = rendir(items[1], '50')
    # Ambos gastos rendidos quedan en revisión.
    assert r.json['solicitud']['etapas'] == ['revision']
    # Ítem 1 aprobado, ítem 2 rechazado: queda S/ 50 pendiente y vuelve a "por rendir"
    parcial = gestion('revisar_item', item=items[0]['id'], aprobar=True)
    assert parcial.status_code == 200
    assert parcial.json['solicitud']['montos_etapa'] == {'sustento': '50.00', 'revision': '50.00'}
    assert gestion('revisar_item', item=items[1]['id'], aprobar=False).status_code == 400  # sin motivo
    r = gestion('revisar_item', item=items[1]['id'], aprobar=False, motivo='Comprobante ilegible')
    s = r.json['solicitud']
    assert s['etapas'] == ['por_rendir', 'sustento'] and s['pendiente'] == '50.00' and s['avance'] == '1 de 2 ítems aprobados'
    assert rendir(items[0], '50').status_code == 400  # el aprobado no se vuelve a rendir
    assert rendir(items[1], '40').status_code == 200  # gastó menos
    r = gestion('revisar_item', item=items[1]['id'], aprobar=True)
    s = r.json['solicitud']
    assert s['estado'] == 'POR_DEVOLVER' and s['diferencia'] == '10.00'
    # Devolución exacta y confirmación → archivado
    url = '/form-pruebas/caja-chica/%d/devolucion' % sid
    assert cli.post(url, headers=h, data={'monto': '5', 'foto': foto()}).status_code == 400
    assert cli.post(url, headers=h, data={'monto': '10', 'foto': foto()}).status_code == 200
    r = gestion('devolucion', aceptar=True)
    # Todo resuelto: pasa a Sustentado y la gestión lo archiva.
    assert r.json['solicitud']['estado'] == 'SUSTENTO' and r.json['solicitud']['etapas'] == ['sustento']
    r = gestion('archivar')
    assert r.json['solicitud']['estado'] == 'ARCHIVADO' and r.json['solicitud']['etapas'] == ['archivado']
    assert gestion('archivar').status_code == 400
    assert gestion('sustento').status_code == 404  # "Volver a Sustentado" ya no existe
    # Rechazar desde Archivado: los ítems vuelven al técnico (Por rendir) con el motivo.
    assert gestion('rechazar_sustentada').status_code == 400  # sin motivo
    rechazo = gestion('rechazar_sustentada', motivo='Falta la boleta original').json['solicitud']
    assert rechazo['estado'] == 'DEPOSITADO' and 'por_rendir' in rechazo['etapas'] and rechazo['archivado_en'] == ''
    assert all(i['estado'] == 'RECHAZADO' and i['motivo_rechazo'] == 'Falta la boleta original' for i in rechazo['items'])
    assert rendir(items[0], '50').status_code == 200 and rendir(items[1], '40').status_code == 200
    assert gestion('revisar_item', item=items[0]['id'], aprobar=True).status_code == 200
    r = gestion('revisar_item', item=items[1]['id'], aprobar=True)
    assert r.json['solicitud']['estado'] == 'SUSTENTO'
    assert gestion('archivar').status_code == 200
    reporte = auth_client.post('/api/caja-chica/exportar', json=[sid], headers={'X-CSRF-Token': token})
    assert reporte.status_code == 200
    libro_final = load_workbook(io.BytesIO(reporte.data))
    filas = list(libro_final['Historial'].values)
    columnas = filas[0]
    items_excel = [dict(zip(columnas, fila)) for fila in filas[1:]]
    assert len(items_excel) == 2 and {'Fecha solicitud', 'Site', 'N.º CM/PM/PLM', 'Motivo de rechazo'} <= set(columnas)
    assert sum(i['Gastado'] for i in items_excel) == 90 and sum(i['Devuelto'] for i in items_excel) == 10
    assert all(i['Solicitado'] == i['Gastado'] + i['Devuelto'] for i in items_excel)
    assert sorted(i['Estado de rendición'] for i in items_excel) == ['Rendido', 'Rendido con saldo']
    assert sum(i['Depositado'] for i in items_excel) == 100 and all(i['Estado de solicitud'] == 'Archivado' for i in items_excel)
    assert all(i['Fecha depósito'] and i['Fecha rendición'] for i in items_excel)
    assert all(i['Plazo 24 h'] == 'Dentro de plazo' and i['Tiempo de rendición'].endswith('h') for i in items_excel)
    # Las fotos se ven desde la gestión y desde el portal del dueño
    nombre = r.json['solicitud']['items'][0]['fotos'][0]
    rendido = r.json['solicitud']['items'][0]
    assert rendido['razon_social'] == 'FERRETERIA EL PERNO SAC' and rendido['evidencia']
    assert auth_client.get('/form-pruebas/caja-chica/foto/%d/%s' % (sid, rendido['evidencia'])).status_code == 200
    assert auth_client.get('/form-pruebas/caja-chica/foto/%d/%s' % (sid, nombre)).status_code == 200
    assert cli.get('/form-pruebas/caja-chica/foto/%d/%s' % (sid, nombre)).status_code == 200
    assert cli.get('/form-pruebas/caja-chica/foto/%d/otra.jpg' % sid).status_code == 404


def test_item_rechazado_que_no_se_sustenta_pasa_a_devolucion(app, auth_client, tecnico):
    cli, h = tecnico
    sol = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}, {'tipo_gasto': 'Peajes', 'monto': '50'}]}).json['solicitud']
    sid = sol['id']
    gestion = lambda accion, **cuerpo: auth_client.post('/api/caja-chica/%d/%s' % (sid, accion), json=cuerpo)
    assert gestion('validar').status_code == 200
    items = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '100', 'foto': foto()}).json['solicitud']['items']
    devolver = lambda item: cli.post('/form-pruebas/caja-chica/%d/item/%d/devolver' % (sid, item['id']), headers=h)
    # Un ítem por rendir también se puede devolver completo, y deshacer mientras no se envía la devolución.
    r = devolver(items[1])
    assert r.status_code == 200 and r.json['solicitud']['items'][1]['estado'] == 'DEVUELTO'
    deshacer = lambda item: cli.post('/form-pruebas/caja-chica/%d/item/%d/deshacer' % (sid, item['id']), headers=h)
    r = deshacer(items[1])
    assert r.status_code == 200 and r.json['solicitud']['items'][1]['estado'] == 'POR_RENDIR'
    assert deshacer(items[1]).status_code == 400
    for item in items:
        assert cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h, data={
            'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': '50',
            'fotos': [foto()], 'evidencia': foto('uso.png')}).status_code == 200
    assert gestion('revisar_item', item=items[0]['id'], aprobar=True).status_code == 200
    assert gestion('revisar_item', item=items[1]['id'], aprobar=False, motivo='Boleta ilegible').status_code == 200
    r = devolver(items[1])
    assert r.status_code == 200, r.json
    s = r.json['solicitud']
    assert s['items'][1]['estado'] == 'DEVUELTO'
    assert s['estado'] == 'POR_DEVOLVER' and s['diferencia'] == '50.00'
    # Deshacer antes de enviar la devolución reabre la rendición; después ya no se puede.
    r = deshacer(items[1])
    assert r.status_code == 200 and r.json['solicitud']['estado'] == 'DEPOSITADO'
    assert devolver(items[1]).json['solicitud']['estado'] == 'POR_DEVOLVER'
    assert cli.post('/form-pruebas/caja-chica/%d/devolucion' % sid, headers=h, data={'monto': '50', 'foto': foto()}).status_code == 200
    assert deshacer(items[1]).status_code == 400


def test_saldo_no_gastado_de_un_item_se_suma_a_la_devolucion(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}, {'tipo_gasto': 'Peajes', 'monto': '50'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    items = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '100', 'foto': foto()}).json['solicitud']['items']
    assert cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, items[0]['id']), headers=h, data={
        'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': '40',
        'fotos': [foto()], 'evidencia': foto('uso.png')}).status_code == 200
    assert auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': items[0]['id'], 'aprobar': True}).status_code == 200
    s = cli.post('/form-pruebas/caja-chica/%d/item/%d/devolver' % (sid, items[1]['id']), headers=h).json['solicitud']
    assert s['estado'] == 'POR_DEVOLVER' and s['diferencia'] == '60.00'  # 10 de saldo + 50 del ítem devuelto
    # Lo aprobado espera en Sustentado la devolución: igual se puede rechazar y vuelve a Por rendir.
    r = auth_client.post('/api/caja-chica/%d/rechazar_sustentada' % sid, json={'motivo': 'Boleta no corresponde'})
    assert r.status_code == 200, r.json
    s = r.json['solicitud']
    assert s['estado'] == 'DEPOSITADO' and s['items'][0]['estado'] == 'RECHAZADO'

    # Y también se puede archivar lo aprobado aunque falte la devolución.
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    item = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '50', 'foto': foto()}).json['solicitud']['items'][0]
    assert cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h, data={
        'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': '40',
        'fotos': [foto()], 'evidencia': foto('uso.png')}).status_code == 200
    s = auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': item['id'], 'aprobar': True}).json['solicitud']
    assert s['estado'] == 'POR_DEVOLVER'
    r = auth_client.post('/api/caja-chica/%d/archivar' % sid)
    assert r.status_code == 200, r.json
    assert r.json['solicitud']['estado'] == 'ARCHIVADO'



def test_rendir_varios_comprobantes_con_su_foto_y_evidencias(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '100'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    item = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '100', 'foto': foto()}).json['solicitud']['items'][0]
    url = '/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id'])

    def datos(montos=('45', '40'), numeros=('B001-452', 'B001-453'), fotos=True, evidencias=2,
              rucs=('20123456789', '20600000001')):
        d = {'comp_ruc': list(rucs), 'comp_numero': list(numeros), 'comp_monto': list(montos),
             'comp_razon': ['PEAJES DEL SUR S.A.', ''], 'evidencia': [foto('e%d.png' % i) for i in range(evidencias)]}
        if fotos:
            d['comp_foto_0'], d['comp_foto_1'] = foto('b1.png'), foto('b2.png')
        return d
    assert cli.post(url, headers=h, data=datos(montos=('60', '50'))).status_code == 400  # suma más que el ítem
    repetida = cli.post(url, headers=h, data=datos(numeros=('B001-452', 'B001-452'), rucs=('20123456789',) * 2))
    assert repetida.status_code == 400 and 'ya está' in repetida.json['error']
    sin_foto = cli.post(url, headers=h, data=datos(fotos=False))
    assert sin_foto.status_code == 400 and 'foto' in sin_foto.json['error']
    assert cli.post(url, headers=h, data=datos(evidencias=0)).status_code == 400  # al menos 1 evidencia
    r = cli.post(url, headers=h, data=datos(evidencias=6))  # sin tope de evidencias
    assert r.status_code == 200, r.json
    rendido = r.json['solicitud']['items'][0]
    assert rendido['monto_gastado'] == '85.00' and rendido['estado'] == 'EN_REVISION'
    assert [c['comprobante'] for c in rendido['comprobantes']] == ['B001-452', 'B001-453']
    assert [c['monto'] for c in rendido['comprobantes']] == ['45.00', '40.00']
    assert len(rendido['fotos']) == 2 and len(rendido['evidencias']) == 6
    for nombre in rendido['fotos'] + rendido['evidencias']:
        assert cli.get('/form-pruebas/caja-chica/foto/%d/%s' % (sid, nombre)).status_code == 200
    assert auth_client.get('/caja-chica/').status_code == 200
    with auth_client.session_transaction() as sesion:
        token = sesion['form_csrf']
    libro = load_workbook(io.BytesIO(auth_client.post('/api/caja-chica/exportar', json=[sid], headers={'X-CSRF-Token': token}).data))
    fila = dict(zip(*[[c.value for c in f] for f in list(libro['Historial'].rows)[:2]]))
    assert fila['N.º boleta'] == 'B001-452 / B001-453' and fila['RUC'] == '20123456789 / 20600000001'
    assert fila['Gastado'] == 85

BASE = {'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678', 'site': 'LA2859', 'wo': 'CM-20260904-00000410',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}]}


def test_eliminar_solicitud_solo_admin_y_conserva_historial(app, auth_client, tecnico, cambiar_rol):
    cli, headers = tecnico
    sol = cli.post('/form-pruebas/caja-chica/solicitar', headers=headers, json=BASE).json['solicitud']
    otra = cli.post('/form-pruebas/caja-chica/solicitar', headers=headers, json=BASE).json['solicitud']
    lote = '/api/caja-chica/eliminar'
    ruta = f"/api/caja-chica/{sol['id']}/eliminar"
    assert auth_client.get('/caja-chica/').status_code == 200
    with auth_client.session_transaction() as sesion:
        csrf = {'X-CSRF-Token': sesion['form_csrf']}
    assert auth_client.post(ruta).status_code == 403
    cambiar_rol(auth_client, 'suport')
    assert auth_client.post(lote, headers=csrf, json=[sol['id']]).status_code == 403
    cambiar_rol(auth_client, 'zeno')
    assert auth_client.post(lote, headers=csrf, json=[sol['id'], 2147483647]).status_code == 404
    assert len(cli.get('/form-pruebas/caja-chica/datos').json['solicitudes']) == 2
    assert auth_client.post(lote, headers=csrf, json=[sol['id'], otra['id']]).status_code == 200
    assert auth_client.post(ruta, headers=csrf).status_code == 404
    assert all(s['id'] != sol['id'] for s in auth_client.get('/api/caja-chica/solicitudes').json['solicitudes'])
    assert cli.get('/form-pruebas/caja-chica/datos').json['solicitudes'] == []
    with app.app_context():
        registro = db.session.get(CajaChicaSolicitud, sol['id'])
        assert registro.codigo == sol['codigo']
        assert json.loads(registro.historial)[-1]['accion'] == 'eliminar'


def test_rechazo_en_validacion_vuelve_al_tecnico(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json=BASE).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/rechazar' % sid, json={}).status_code == 400  # sin motivo
    s = auth_client.post('/api/caja-chica/%d/rechazar' % sid, json={'motivo': 'Monto alto'}).json['solicitud']
    # Sigue visible en Validación, pero está con el técnico: no se valida hasta que la corrija.
    assert s['estado'] == 'RECHAZADO' and s['etapas'] == ['validacion'] and s['retorno'] == 'con_tecnico'
    assert auth_client.post('/api/caja-chica/%d/validar' % sid, json={}).status_code == 400
    # El técnico corrige (cambia ítems) y reenvía: vuelve a Validación como reenviada.
    url = '/form-pruebas/caja-chica/%d/reenviar' % sid
    assert cli.post(url, headers=h, json={**BASE, 'items': []}).status_code == 400
    r = cli.post(url, headers=h, json={**BASE, 'items': [{'tipo_gasto': 'Peajes', 'monto': '15'}, {'tipo_gasto': 'Peajes', 'monto': '3'}]})
    s = r.json['solicitud']
    assert r.status_code == 200 and s['estado'] == 'PENDIENTE' and s['retorno'] == 'reenviada'
    assert s['total'] == '18.00' and len(s['items']) == 2 and s['motivo_rechazo'] == ''
    assert cli.post(url, headers=h, json=BASE).status_code == 400  # ya no está rechazada
    s = auth_client.post('/api/caja-chica/%d/validar' % sid, json={}).json['solicitud']
    assert s['estado'] == 'VALIDADO' and s['retorno'] == ''


def test_rechazo_en_deposito_vuelve_a_validacion(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json=BASE).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid, json={}).status_code == 200
    s = auth_client.post('/api/caja-chica/%d/rechazar' % sid, json={'motivo': 'Cuenta no coincide'}).json['solicitud']
    assert s['estado'] == 'PENDIENTE' and s['etapas'] == ['validacion'] and s['retorno'] == 'desde_deposito'
    assert s['motivo_rechazo'] == 'Cuenta no coincide'
    # Validación puede volver a validarla (limpia el rechazo) o devolverla al técnico.
    s = auth_client.post('/api/caja-chica/%d/validar' % sid, json={}).json['solicitud']
    assert s['estado'] == 'VALIDADO' and s['motivo_rechazo'] == '' and s['retorno'] == ''


def test_anulacion_va_a_anuladas(app, auth_client, tecnico):
    cli, h = tecnico
    a, b = (cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json=BASE).json['solicitud']['id'] for _ in range(2))
    r = auth_client.post('/api/caja-chica/%d/anular' % a, json={'motivo': 'Ya no se necesita'})
    assert r.json['solicitud']['etapas'] == ['anuladas']
    auth_client.post('/api/caja-chica/%d/rechazar' % b, json={'motivo': 'x'})  # también se anula estando con el técnico
    assert auth_client.post('/api/caja-chica/%d/anular' % b, json={'motivo': 'y'}).json['solicitud']['etapas'] == ['anuladas']


def test_validaciones_de_la_solicitud(tecnico):
    cli, h = tecnico
    base = {'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678', 'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}]}
    for cambio in ({'motivo': ''}, {'banco': 'Inventado'}, {'cuenta': 'abc'},
                   {'cuenta': '1' * 19}, {'cuenta': '1' * 21}, {'items': []},
                   {'items': [{'tipo_gasto': 'Inventado', 'monto': '5'}]}, {'items': [{'tipo_gasto': 'Peajes', 'monto': '0'}]}):
        assert cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={**base, **cambio}).status_code == 400, cambio
    assert cli.post('/form-pruebas/caja-chica/solicitar', json=base).status_code == 403  # sin CSRF


def test_usuario_sin_modulo_no_entra(app, client):
    from werkzeug.security import generate_password_hash
    from models import Usuario
    with app.app_context():
        u = Usuario(username='sin-caja', password_hash=generate_password_hash('x'), rol='gestor')
        db.session.add(u); db.session.commit(); uid = u.id
    try:
        with client.session_transaction() as s:
            s.update(user_id=uid, rol='gestor')
        assert client.get('/caja-chica/').status_code == 403
        assert client.get('/api/caja-chica/solicitudes').status_code == 403
    finally:
        with app.app_context():
            Usuario.query.filter_by(id=uid).delete(); db.session.commit()


def test_devolucion_se_envia_al_terminar_de_rendir_sin_esperar_la_revision(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}, {'tipo_gasto': 'Peajes', 'monto': '50'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    items = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '100', 'foto': foto()}).json['solicitud']['items']
    rendir = lambda item, monto: cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h, data={
        'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': monto, 'fotos': [foto()], 'evidencia': foto('uso.png')})
    devolver = lambda monto: cli.post('/form-pruebas/caja-chica/%d/devolucion' % sid, headers=h, data={'monto': monto, 'foto': foto()})
    s = rendir(items[0], '40').json['solicitud']
    assert not s['puede_devolver'] and devolver('10').status_code == 400  # aún falta rendir un ítem
    s = rendir(items[1], '50').json['solicitud']
    assert s['estado'] == 'DEPOSITADO' and s['puede_devolver'] and s['diferencia'] == '10.00'
    r = devolver('10')
    assert r.status_code == 200 and r.json['solicitud']['devolucion_monto'] == '10.00'
    for item in items:
        r = auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': item['id'], 'aprobar': True})
        assert r.status_code == 200
    s = r.json['solicitud']
    assert s['estado'] == 'POR_DEVOLVER' and s['devolucion_foto']  # queda lista para aceptar


def test_devolucion_anticipada_se_pide_de_nuevo_si_cambia_el_monto(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}, {'tipo_gasto': 'Peajes', 'monto': '50'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    items = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '100', 'foto': foto()}).json['solicitud']['items']
    for item, monto in zip(items, ('40', '50')):
        assert cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h, data={
            'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': monto, 'fotos': [foto()], 'evidencia': foto('uso.png')}).status_code == 200
    assert cli.post('/form-pruebas/caja-chica/%d/devolucion' % sid, headers=h, data={'monto': '10', 'foto': foto()}).status_code == 200
    assert auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': items[0]['id'], 'aprobar': True}).status_code == 200
    assert auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': items[1]['id'], 'aprobar': False, 'motivo': 'x'}).status_code == 200
    s = cli.post('/form-pruebas/caja-chica/%d/item/%d/devolver' % (sid, items[1]['id']), headers=h).json['solicitud']
    assert s['estado'] == 'POR_DEVOLVER' and s['diferencia'] == '60.00' and not s['devolucion_foto'] and s['puede_devolver']


def test_devolucion_anticipada_se_aprueba_o_rechaza_antes_de_revisar_los_items(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '50'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    item = auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '50', 'foto': foto()}).json['solicitud']['items'][0]
    assert cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h, data={
        'ruc': '20123456789', 'comprobante': 'F001-1', 'monto_gastado': '40', 'fotos': [foto()], 'evidencia': foto('uso.png')}).status_code == 200
    devolver = lambda: cli.post('/form-pruebas/caja-chica/%d/devolucion' % sid, headers=h, data={'monto': '10', 'foto': foto()})
    gestion = lambda **cuerpo: auth_client.post('/api/caja-chica/%d/devolucion' % sid, json=cuerpo)
    assert devolver().status_code == 200
    # Rechazo: la transferencia no llegó. El técnico vuelve a subir la captura.
    r = gestion(aceptar=False, motivo='No llegó la transferencia')
    assert r.status_code == 200, r.json
    s = r.json['solicitud']
    assert s['estado'] == 'DEPOSITADO' and not s['devolucion_foto'] and s['puede_devolver']
    assert devolver().status_code == 200
    s = gestion(aceptar=True).json['solicitud']
    assert s['estado'] == 'DEPOSITADO' and s['devolucion_aceptada']
    assert gestion(aceptar=True).status_code == 400  # ya aprobada
    s = auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': item['id'], 'aprobar': True}).json['solicitud']
    assert s['estado'] == 'SUSTENTO'  # ítems validados + devolución aprobada: queda para archivar


def _proyecto_tecnico(app, proyecto):
    """Cambia el proyecto del técnico de prueba en Dataper (el portal lo toma de ahí)."""
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value=DOC).one()
        fila.data_json = json.dumps({**json.loads(fila.data_json), 'PROYECTO': proyecto})
        db.session.commit()


def test_el_proyecto_sale_de_dataper(app, tecnico):
    cli, h = tecnico
    datos = {'proyecto': 'ENTEL', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
             'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}]}
    r = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json=datos)
    assert r.status_code == 200 and r.json['solicitud']['proyecto'] == 'CLARO', r.json  # se ignora lo que mande
    _proyecto_tecnico(app, '')
    try:
        assert cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json=datos).status_code == 400
    finally:
        _proyecto_tecnico(app, 'FLM - CLARO')


def test_catalogo_correo_y_cotizacion_por_proyecto(app, auth_client, tecnico):
    cli, headers = tecnico
    ruta = '/caja-chica/catalogo'
    token = re.search(rb'data-csrf="([^"]+)"', auth_client.get(ruta).data).group(1).decode()
    base = '/form-pruebas/caja-chica'
    catalogo = cli.get(base + '/datos').json['catalogo']
    peajes = next(c for c in catalogo if c['nombre'] == 'Peajes')
    assert peajes['correo'] == {'ENTEL': False, 'CLARO': False, 'INTEGRATEL': False, 'PEXT': False}
    peajes['correo'] = {'ENTEL': True, 'CLARO': False, 'INTEGRATEL': False, 'PEXT': False}
    peajes['cotizacion'] = {'ENTEL': False, 'CLARO': True, 'INTEGRATEL': False, 'PEXT': False}
    try:
        assert auth_client.post(ruta, json=catalogo, headers={'X-CSRF-Token': token}).status_code == 200
        guardado = next(c for c in cli.get(base + '/datos').json['catalogo'] if c['nombre'] == 'Peajes')
        assert guardado['correo']['ENTEL'] is True and guardado['correo']['CLARO'] is False
        datos = {'proyecto': 'ENTEL', 'motivo': 'Correctivo', 'banco': 'BCP', 'cuenta': '00123456789012345678',
                 'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}], 'site': 'LA2859', 'wo': 'CM-20260904-00000410', 'titular': 'Técnico Caja'}
        _proyecto_tecnico(app, 'FLM - ENTEL')
        respuesta = cli.post(base + '/solicitar', headers=headers, json=datos)
        assert respuesta.status_code == 200, respuesta.json  # el técnico no da correo; Entel lo pedirá al validar
        assert respuesta.json['solicitud']['items'][0]['requiere_correo'] is True
        _proyecto_tecnico(app, 'FLM - CLARO')
        respuesta = cli.post(base + '/solicitar', headers=headers, json=datos)
        assert respuesta.status_code == 200, respuesta.json  # Claro no pide correo
        item = respuesta.json['solicitud']['items'][0]
        assert item['requiere_correo'] is False and item['requiere_cotizacion'] is True
    finally:
        with app.app_context():
            modulo = Proyecto.query.filter_by(nombre='Caja Chica').one()
            AppConfig.query.filter_by(proyecto_id=modulo.id, clave='catalogo_gastos').delete()
            db.session.commit()


def test_cm_y_site_pendiente():
    from services import caja_chica as cc
    assert cc.normalizar_cm('') == 'CM PENDIENTE'
    assert cc.normalizar_cm('cm 20261025-00000037') == 'CM-20261025-00000037'
    assert cc.normalizar_cm('CM-20261025-00000037 y PM_20261101_00000002') == 'CM-20261025-00000037, PM-20261101-00000002'
    for malo in ('Por regularizar', 'N/A', '.', '20261025-00000037'):
        with pytest.raises(ValueError):
            cc.normalizar_cm(malo)
    assert cc.cm_pendiente('CM PENDIENTE') and cc.cm_pendiente('Pendiente') and not cc.cm_pendiente('CM-20261025-00000037')
    formulario = cc.datos_formulario({'site': '', 'wo': ''}, '', {})
    assert formulario['site'] == 'SITE PENDIENTE' and formulario['wo'] == 'CM PENDIENTE'


def test_resumen_para_el_menu(auth_client, tecnico):
    cli, h = tecnico
    antes = auth_client.get('/api/caja-chica/resumen').json['por_validar']
    datos = {'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678', 'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}]}
    assert cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json=datos).status_code == 200
    assert auth_client.get('/api/caja-chica/resumen').json['por_validar'] == antes + 1
    pagina = auth_client.get('/caja-chica/').get_data(as_text=True)
    # El número del menú se quitó a pedido: el menú no muestra el contador.
    assert 'id="sb-cc-pendientes"' not in pagina and 'data-grupo="flm"' in pagina


def test_solicitud_migrada_muestra_las_fotos_de_rendicion(app, auth_client, tecnico, monkeypatch):
    """Lo migrado desde Rendición no trae fotos en el ítem: se toman del registro original (mismo código)."""
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '25'}]}).json['solicitud']['id']
    with app.app_context():
        sol = db.session.get(CajaChicaSolicitud, sid)
        codigo = sol.codigo
        modulo = Proyecto.query.filter_by(nombre='Rendicion').first()
        if not modulo:
            modulo = Proyecto(nombre='Rendicion'); db.session.add(modulo); db.session.flush()
        pid = modulo.id
        fila = NucleusData(proyecto_id=pid, key_value='6/10/2026 14:30:00', data_json=json.dumps({
            'CODIGO DEPOSITO': codigo, 'FOTO PAGO': '/api/rendicion/foto/%d/x/pago.jpg' % pid,
            'FOTOS SUSTENTO': json.dumps(['/api/rendicion/foto/%d/6_10_2026_14_30_00/boleta.jpg?v=1' % pid]),
            'SUSTENTO_FOTO EVIDENCIA': 'https://drive.google.com/open?id=abc'}))
        db.session.add(fila); db.session.commit()
        rid = fila.id
    try:
        fotos = auth_client.get('/api/caja-chica/%d/fotos-origen' % sid).json['fotos']
        assert [f['etiqueta'] for f in fotos] == ['Foto de sustento', 'Evidencia']  # la foto del pago no entra
        assert fotos[1]['url'] == 'https://drive.google.com/open?id=abc'
        servidas = []
        import blueprints.rendicion as rendicion
        monkeypatch.setattr(rendicion, '_servir_foto_rendicion', lambda p, c, a: (servidas.append((p, c, a)), 'ok')[1])
        assert auth_client.get(fotos[0]['url']).status_code == 200
        assert servidas == [(pid, '6_10_2026_14_30_00', 'boleta.jpg')]
        # Un nombre inventado no se sirve, ni el técnico usa esta vía.
        assert auth_client.get('/form-pruebas/caja-chica/foto/%d/ren~%d~x~otra.jpg' % (sid, pid)).status_code == 404
    finally:
        with app.app_context():
            NucleusData.query.filter_by(id=rid).delete(); db.session.commit()


def test_admin_corrige_el_dni_mal_escrito_con_dataper(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}]}).json['solicitud']['id']
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Dataper').one().id
        otro = NucleusData(proyecto_id=pid, key_value='41265049', data_json=json.dumps(
            {'DOCUMENTO': '41265049', 'TECNICO': 'LUIS MARINO CAMACUARI GONZALES', 'ESTADO': 'ACTIVO', 'PROYECTO': 'FLM - CLARO'}))
        db.session.add(otro); db.session.commit()
        oid = otro.id
    try:
        assert auth_client.get('/caja-chica/').status_code == 200
        with auth_client.session_transaction() as sesion:
            token = sesion['form_csrf']
        url = '/api/caja-chica/%d/tecnico' % sid
        mal = auth_client.post(url, json={'documento': '88888888'}, headers={'X-CSRF-Token': token})
        assert mal.status_code == 400 and 'Dataper' in mal.json['error']
        r = auth_client.post(url, json={'documento': '41265049'}, headers={'X-CSRF-Token': token})
        assert r.status_code == 200, r.json
        assert r.json['solicitud']['documento'] == '41265049'
        assert r.json['solicitud']['tecnico'] == 'LUIS MARINO CAMACUARI GONZALES'
        assert r.json['solicitud']['historial'][-1]['accion'] == 'corregir técnico'
    finally:
        with app.app_context():
            CajaChicaSolicitud.query.filter_by(documento='41265049').delete()
            NucleusData.query.filter_by(id=oid).delete(); db.session.commit()


def test_monto_de_cotizacion_es_el_sub_total_con_fee():
    from services.rendicion_presupuesto_cotizacion import monto_cotizacion
    items = json.dumps([{'cantidad': '70', 'valor_unitario': '33.21', 'valor_total': '2440.94'}])
    assert monto_cotizacion('2440.94', items) == '2440.94'  # caso CL-2026-11-000658
    assert monto_cotizacion('2,802.25', '[]') == '2802.25'
    assert monto_cotizacion('', items) == '2440.94'  # sin SUB TOTAL + FEE: suma de valores totales
    assert monto_cotizacion(None, None) is None


def test_depositante_entra_desde_el_celular_y_deposita_con_el_mismo_flujo(app, auth_client, tecnico):
    from models import Usuario
    with app.app_context():
        uid = Usuario.query.filter_by(username='zeno').one().id
    try:
        assert auth_client.post('/api/vista/usuarios/depositante', json={'id': uid, 'activo': True}).status_code == 200
        marcado = next(u for u in auth_client.get('/api/vista/usuarios/lista').json['usuarios'] if u['id'] == uid)
        assert marcado['depositante'] is True
        celular = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Mobile Safari'}
        nuevo = app.test_client()
        r = nuevo.post('/login', data={'username': 'zeno', 'password': 'zeno123', 'legal_accept': '1'}, headers=celular)
        if r.status_code == 200 and b'name="consent_step"' in r.data:
            r = nuevo.post('/login', data={'consent_step': '1', 'legal_accept': '1'}, headers=celular)
        assert r.headers['Location'].endswith('/caja-chica/movil')
        assert nuevo.get('/caja-chica/movil').status_code == 200
        # Desde computadora entra a Nucleus normal.
        pc = app.test_client()
        r = pc.post('/login', data={'username': 'zeno', 'password': 'zeno123', 'legal_accept': '1'})
        if r.status_code == 200 and b'name="consent_step"' in r.data:
            r = pc.post('/login', data={'consent_step': '1', 'legal_accept': '1'})
        assert '/caja-chica/movil' not in r.headers['Location']
        # Deposita con el mismo flujo: solo validadas, monto exacto y captura.
        cli, h = tecnico
        sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
            'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
            'items': [{'tipo_gasto': 'Peajes', 'monto': '20'}]}).json['solicitud']['id']
        assert nuevo.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '20', 'foto': foto()}).status_code == 400  # sin validar
        assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
        r = nuevo.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '20', 'foto': foto()})
        assert r.status_code == 200 and r.json['solicitud']['estado'] == 'DEPOSITADO'
    finally:
        auth_client.post('/api/vista/usuarios/depositante', json={'id': uid, 'activo': False})


def test_conceptos_marcados_sin_monto_no_se_consideran(tecnico):
    cli, h = tecnico
    base = {'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678'}
    r = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={**base, 'items': [
        {'tipo_gasto': 'Peajes', 'monto': '30'}, {'tipo_gasto': 'Peajes', 'monto': '0'}, {'tipo_gasto': 'Peajes', 'monto': ''}]})
    assert r.status_code == 200, r.json
    assert [i['monto'] for i in r.json['solicitud']['items']] == ['30.00'] and r.json['solicitud']['total'] == '30.00'
    vacia = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={**base, 'items': [{'tipo_gasto': 'Peajes', 'monto': '0'}]})
    assert vacia.status_code == 400 and 'monto' in vacia.json['error']


def test_cotizado_en_caja_chica_es_cantidad_por_valor_unitario_sin_fee():
    from services.rendicion_presupuesto_cotizacion import suma_valores_unitarios
    items = json.dumps([{'cantidad': '1', 'valor_unitario': '360', 'valor_total': '378.00'},
                        {'cantidad': '70', 'valor_unitario': '33.21', 'valor_total': '2440.94'}])
    assert suma_valores_unitarios(items) == '2684.70'  # 1 × 360 + 70 × 33.21 (2,324.70), sin FEE
    assert suma_valores_unitarios('[]') is None


def test_orden_de_columnas_es_el_mismo_para_todos(auth_client, cambiar_rol):
    assert auth_client.get('/caja-chica/').status_code == 200
    with auth_client.session_transaction() as sesion:
        csrf = {'X-CSRF-Token': sesion['form_csrf']}
    ruta = '/api/caja-chica/columnas'
    cambiar_rol(auth_client, 'zeno')
    assert auth_client.post(ruta, headers=csrf, json={'columnas': ['<x>']}).status_code == 400
    assert auth_client.post(ruta, headers=csrf, json={'columnas': ['total', 'codigo']}).status_code == 200
    assert 'data-columnas="[&#34;total&#34;, &#34;codigo&#34;]"' in auth_client.get('/caja-chica/').get_data(as_text=True)
    cambiar_rol(auth_client, 'demo')
    assert auth_client.post(ruta, headers=csrf, json={'columnas': ['codigo']}).status_code == 403


def test_conceptos_los_ven_todos_y_solo_edita_el_supervisor(auth_client, cambiar_rol, monkeypatch):
    import blueprints.caja_chica as modulo
    original = modulo.get_menu_proyectos
    # Cualquier rol con el módulo Caja Chica asignado.
    monkeypatch.setattr(modulo, 'get_menu_proyectos', lambda uid, rol: original(uid, 'zeno'))
    ruta = '/caja-chica/catalogo'
    token = re.search(rb'data-csrf="([^"]+)"', auth_client.get(ruta).data).group(1).decode()
    catalogo = [{'nombre': 'Peajes', 'descripcion': '', 'proyectos': {'ENTEL': 'Gasto Cobra'}}]
    cambiar_rol(auth_client, 'gestor')
    pagina = auth_client.get(ruta).get_data(as_text=True)
    assert 'Solo lectura' in pagina and 'cc-catalogo-agregar' not in pagina
    assert 'Conceptos de gasto' in auth_client.get('/caja-chica/').get_data(as_text=True)
    assert auth_client.post(ruta, json=catalogo, headers={'X-CSRF-Token': token}).status_code == 403
    cambiar_rol(auth_client, 'admin')
    assert auth_client.post(ruta, json=catalogo, headers={'X-CSRF-Token': token}).status_code == 403
    cambiar_rol(auth_client, 'supervisor')
    pagina = auth_client.get(ruta).get_data(as_text=True)
    assert 'cc-catalogo-agregar' in pagina and 'Solo lectura' not in pagina
    cambiar_rol(auth_client, 'demo')
    assert auth_client.get(ruta).status_code == 403
    cambiar_rol(auth_client, 'zeno')


def test_corregir_monto_segun_boleta_y_comentario_del_deposito(app, auth_client, tecnico):
    cli, h = tecnico
    sid = cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': 'Peajes', 'monto': '77'}]}).json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    s = auth_client.post('/api/caja-chica/%d/depositar' % sid,
                         data={'monto': '77', 'foto': foto(), 'comentario': 'Desde la cuenta BBVA'}).json['solicitud']
    assert s['deposito_comentario'] == 'Desde la cuenta BBVA'
    assert cli.get('/form-pruebas/caja-chica/datos', headers=h).json['solicitudes'][0]['deposito_comentario'] == 'Desde la cuenta BBVA'
    item = s['items'][0]
    assert cli.post('/form-pruebas/caja-chica/%d/item/%d/rendir' % (sid, item['id']), headers=h, data={
        'ruc': '20123456789', 'comprobante': 'F001-568', 'monto_gastado': '77', 'fotos': [foto()], 'evidencia': foto('uso.png')}).status_code == 200
    url = '/api/caja-chica/%d/corregir_monto' % sid
    assert auth_client.post(url, json={'item': item['id'], 'montos': ['80']}).status_code == 400  # más que lo solicitado
    assert auth_client.post(url, json={'item': item['id'], 'montos': ['76']}).status_code == 400  # falta el comentario
    r = auth_client.post(url, json={'item': item['id'], 'montos': ['76'], 'motivo': 'La boleta es por S/ 76'})
    assert r.status_code == 200
    s = r.json['solicitud']
    assert s['items'][0]['monto_gastado'] == '76.00' and s['items'][0]['comprobantes'][0]['monto'] == '76.00'
    assert s['historial'][-1]['motivo'] == 'S/ 77.00 → S/ 76.00: La boleta es por S/ 76'
    tec = cli.get('/form-pruebas/caja-chica/datos', headers=h).json['solicitudes'][0]['items'][0]
    assert tec['correccion'] == 'S/ 77.00 → S/ 76.00: La boleta es por S/ 76'
    s = auth_client.post('/api/caja-chica/%d/revisar_item' % sid, json={'item': item['id'], 'aprobar': True}).json['solicitud']
    assert s['estado'] == 'POR_DEVOLVER' and s['diferencia'] == '1.00'  # el técnico devuelve S/ 1


def _solicitar(cli, h, tipo='Peajes', monto='50'):
    return cli.post('/form-pruebas/caja-chica/solicitar', headers=h, json={
        'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
        'items': [{'tipo_gasto': tipo, 'monto': monto}]})


def _reglas(app, **cambios):
    from services import caja_chica_reglas as reglas
    with app.app_context():
        actual = {n: {'activa': r['activa'], 'valor': str(r['valor']), 'proyectos': r['proyectos']} for n, r in reglas.leer().items()}
        for nombre, valores in cambios.items():
            actual[nombre].update(valores)
        reglas.guardar(actual, 'prueba')


def test_mobile_enlace_corto_lleva_al_portal(app):
    r = app.test_client().get('/mobile/')
    assert r.status_code == 302 and r.headers['Location'].endswith('/form-pruebas/')


def test_mobile_tope_por_rendir_y_proyectos(app, auth_client, tecnico):
    cli, h = tecnico
    sid = _solicitar(cli, h, monto='550').json['solicitud']['id']
    assert auth_client.post('/api/caja-chica/%d/validar' % sid).status_code == 200
    assert auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '550', 'foto': foto()}).status_code == 200
    r = cli.get('/form-pruebas/caja-chica/datos', headers=h).json['restricciones']
    assert r['por_rendir'] == '550.00' and 'S/ 550.00 por rendir' in r['aviso'] and not r['bloqueos']
    assert _solicitar(cli, h).status_code == 200  # con aviso sí puede solicitar
    _reglas(app, tope={'valor': '540'}, aviso={'valor': '400'})
    r = _solicitar(cli, h)
    assert r.status_code == 400 and 'tope es S/ 540.00' in r.json['error']
    # Si la regla no aplica a su proyecto (Claro), no se bloquea.
    _reglas(app, tope={'proyectos': ['ENTEL', 'PEXT']})
    assert _solicitar(cli, h).status_code == 200
    _reglas(app, tope={'activa': True, 'valor': '600', 'proyectos': ['ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT']}, aviso={'valor': '500'})


def test_mobile_plazo_de_48_horas(app, auth_client, tecnico):
    from datetime import datetime, timedelta
    cli, h = tecnico
    sid = _solicitar(cli, h).json['solicitud']['id']
    auth_client.post('/api/caja-chica/%d/validar' % sid)
    auth_client.post('/api/caja-chica/%d/depositar' % sid, data={'monto': '50', 'foto': foto()})
    assert _solicitar(cli, h).status_code == 200
    with app.app_context():
        sol = db.session.get(CajaChicaSolicitud, sid)
        sol.depositado_en = datetime.utcnow() - timedelta(hours=49)
        codigo = sol.codigo
        db.session.commit()
    r = _solicitar(cli, h)
    assert r.status_code == 400 and '48 h' in r.json['error'] and codigo in r.json['error']


def test_mobile_maximo_de_refacturables(app, tecnico):
    cli, h = tecnico
    refact = 'Alquiler de vehículos - Refacturable'
    assert _solicitar(cli, h, refact).status_code == 200
    assert _solicitar(cli, h, refact).status_code == 200
    r = _solicitar(cli, h, refact)
    assert r.status_code == 400 and 'máximo 2' in r.json['error']
    assert _solicitar(cli, h).status_code == 200  # un gasto Cobra sí pasa
    assert cli.get('/form-pruebas/caja-chica/datos', headers=h).json['restricciones']['refacturables'] == {'pendientes': 2, 'maximo': 2}


def test_mobile_admin_guarda_restricciones(app, auth_client):
    pagina = auth_client.get('/form-pruebas/administrar')
    assert pagina.status_code == 200 and b'Restricciones' in pagina.data and b'/mobile/' in pagina.data
    with auth_client.session_transaction() as s:
        token = s.get('form_csrf')
    datos = {'csrf': token, 'accion': 'reglas'}
    for n, v in (('aviso', '300'), ('tope', '400'), ('plazo', '24'), ('refacturables', '1')):
        datos.update({n + '_activa': '1', n + '_valor': v, n + '_proyectos': ['ENTEL', 'CLARO']})
    r = auth_client.post('/form-pruebas/administrar', data=datos)
    assert r.status_code == 302 and 'guardado=1' in r.headers['Location']
    from services import caja_chica_reglas as reglas
    with app.app_context():
        assert reglas.leer()['plazo']['valor'] == 24 and reglas.leer()['tope']['proyectos'] == ['ENTEL', 'CLARO']
    datos['aviso_valor'] = '500'  # el aviso no puede ser mayor que el tope
    assert 'error=' in auth_client.post('/form-pruebas/administrar', data=datos).headers['Location']
    _reglas(app, aviso={'valor': '500', 'proyectos': list(reglas.PROYECTOS)}, tope={'valor': '600', 'proyectos': list(reglas.PROYECTOS)},
            plazo={'valor': '48', 'proyectos': list(reglas.PROYECTOS)}, refacturables={'valor': '2', 'proyectos': list(reglas.PROYECTOS)})
