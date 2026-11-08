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
            {'DOCUMENTO': DOC, 'TECNICO': 'Técnico Caja', 'ESTADO': 'ACTIVO', 'PROYECTO': 'FLM - CLARO'}))
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
                 'site': 'LA2859', 'wo': 'CM-001', 'titular': 'Técnico Caja',
                 'tipo_billetera': 'Yape', 'numero_billetera': '900000000'}
        assert cli.post(base + '/solicitar', headers=headers, json=datos).status_code == 400
        datos['proyecto'] = 'CLARO'
        assert cli.post(base + '/solicitar', headers=headers, json=datos).status_code == 400
        item['correo_validador'] = 'validador@example.com'
        respuesta = cli.post(base + '/solicitar', headers=headers, json=datos)
        assert respuesta.status_code == 200, respuesta.json
        materiales['proyectos']['CLARO'] = 'Refacturable'
        assert auth_client.post(ruta, json=catalogo, headers=permisos).status_code == 200
        guardado = cli.get(base + '/datos').json['solicitudes'][0]['items'][0]
        assert guardado['tipo_presupuesto'] == 'Gasto Cobra'
        assert guardado['correo_validador'] == 'validador@example.com'
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
        'proyecto': 'CLARO', 'motivo': 'Correctivo LA2859', 'banco': 'BCP', 'cuenta': '00123456789012345678',
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
    assert libro['Solicitudes']['A2'].value == sol['codigo']
    assert libro['Solicitudes']['H2'].value == 100
    assert libro['Conceptos'].max_row == 3
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
    assert parcial.json['solicitud']['montos_etapa'] == {'archivado': '50.00', 'revision': '50.00'}
    assert gestion('revisar_item', item=items[1]['id'], aprobar=False).status_code == 400  # sin motivo
    r = gestion('revisar_item', item=items[1]['id'], aprobar=False, motivo='Comprobante ilegible')
    s = r.json['solicitud']
    assert s['etapas'] == ['archivado', 'por_rendir'] and s['pendiente'] == '50.00' and s['avance'] == '1 de 2 ítems aprobados'
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
    assert r.json['solicitud']['estado'] == 'ARCHIVADO' and r.json['solicitud']['etapas'] == ['archivado']
    reporte = auth_client.post('/api/caja-chica/exportar', json=[sid], headers={'X-CSRF-Token': token})
    assert reporte.status_code == 200
    libro_final = load_workbook(io.BytesIO(reporte.data))
    assert libro_final['Solicitudes'].max_row == 2
    assert libro_final['Conceptos'].max_row == 3
    resumen = dict(zip([c.value for c in libro_final['Solicitudes'][1]],
                       [c.value for c in libro_final['Solicitudes'][2]]))
    assert resumen['Monto depositado'] == 100
    assert resumen['Gasto aprobado'] == 90
    assert resumen['Monto devuelto confirmado'] == 10
    assert resumen['Falta rendir'] == 0
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


BASE = {'proyecto': 'CLARO', 'motivo': 'x', 'banco': 'BCP', 'cuenta': '00123456789012345678',
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
    for cambio in ({'proyecto': 'OTRO'}, {'motivo': ''}, {'banco': 'Inventado'}, {'cuenta': 'abc'},
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
