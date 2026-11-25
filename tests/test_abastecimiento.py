import io
import json
import time
from decimal import Decimal

from PIL import Image

from blueprints import asistencia_movil, formularios_prueba
from db import db
from models import AbastecimientoSolicitud, AccesoProyecto, NucleusData, Proyecto, Usuario


def test_generadores_reutiliza_catalogo_y_edita(app, auth_client):
    gestion = auth_client.get('/abastecimiento/?estado=parque').get_data(as_text=True)
    assert 'aria-label="Registrar generador"' not in gestion
    alta = auth_client.get('/abastecimiento/?estado=generadores&nuevo=1')
    assert b'id="ab-form-generador"' in alta.data
    contenido = alta.get_data(as_text=True)
    assert 'Petróleo' in contenido and 'Técnico asignado' not in contenido
    for proyecto in ('Claro', 'Integratel', 'Entel', 'PEXT'):
        assert f'FLM - {proyecto}</option>' in contenido
    pagina = auth_client.get('/abastecimiento/?estado=generadores')
    assert pagina.status_code == 200 and b'Tabla de generadores' in pagina.data
    assert b'aria-label="Registrar generador"' in pagina.data
    assert b'id="ab-form-generador"' not in pagina.data
    assert b'Ordenar Zona' in pagina.data and b'Filtrar Zona' in pagina.data
    with auth_client.session_transaction() as ses:
        headers = {'X-CSRF-Token': ses['form_csrf']}
    ruta = '/abastecimiento/generadores/guardar'
    datos = {'QR ASIGNADO': 'QA-QR-G1', 'SERIE DE EQUIPO': '000113', 'ZONA': 'CENTRO',
             'TIPO': 'CLIENTE', 'PROYECTO': 'CLARO', 'TIPO DE COMBUSTIBLE': 'PETRÓLEO'}
    try:
        assert auth_client.post(ruta, headers=headers, data=datos).status_code == 200
        assert auth_client.post(ruta, headers=headers, data=datos).status_code == 400
        with app.app_context():
            pid = Proyecto.query.filter_by(nombre='Generadores').one().id
            fila = NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.data_json.contains('QA-QR-G1')).one()
            datos_guardados = json.loads(fila.data_json)
            assert datos_guardados['SERIE DE EQUIPO'] == '000113'
            assert datos_guardados['TIPO DE COMBUSTIBLE'] == 'PETRÓLEO'
            datos_guardados['CAMPO ANTERIOR'] = 'conservar'
            fila.data_json = json.dumps(datos_guardados)
            registro = fila.id
            db.session.commit()
        assert b'QA-QR-G1' in auth_client.get(f'/abastecimiento/?estado=generadores&editar={registro}').data
        assert auth_client.post(ruta, headers=headers, data={**datos, 'registro': registro, 'TIPO': 'ALQUILADO'}).status_code == 200
        with app.app_context():
            ficha = json.loads(db.session.get(NucleusData, registro).data_json)
            assert ficha['CAMPO ANTERIOR'] == 'conservar' and ficha['TIPO'] == 'ALQUILADO'
    finally:
        with app.app_context():
            pid = Proyecto.query.filter_by(nombre='Generadores').one().id
            NucleusData.query.filter_by(proyecto_id=pid).filter(NucleusData.data_json.contains('QA-QR-G1')).delete(synchronize_session=False)
            db.session.commit()


def test_abastecimiento_qr_fotos_y_descuento_de_saldo(app, auth_client, monkeypatch):
    persona = {'id': 100009, 'documento': '71234567', 'nombre': 'Técnico QA',
               'proyecto': 'FLM - INTEGRATEL', 'departamento': 'HUANCAVELICA', 'supervisor': 'Supervisor QA'}
    monkeypatch.setattr(formularios_prueba.piloto, 'buscar_personal',
                        lambda doc: persona if doc == persona['documento'] else {**persona, 'id': 100010})
    monkeypatch.setattr(asistencia_movil.am, 'de_hoy', lambda _: True)
    monkeypatch.setitem(app.config, 'FORM_PRUEBAS_ENABLED', True)
    mobile = app.test_client()
    with mobile.session_transaction() as ses:
        ses.update(form_documento=persona['documento'], form_personal_id=persona['id'],
                   form_login_at=time.time(), form_csrf='tecnico-csrf')
    assert mobile.get('/form-pruebas/abastecimiento').status_code == 404
    assert b'/form-pruebas/abastecimiento' not in mobile.get('/form-pruebas/').data
    monkeypatch.setitem(app.config, 'ABASTECIMIENTO_MOBILE_ENABLED', True)

    def operador(rol):
        cuenta = app.test_client()
        with app.app_context():
            user = Usuario(username=f'qa-ab-{rol}', password_hash='prueba', rol=rol)
            db.session.add(user)
            db.session.flush()
            for nombre in ('Abastecimiento', 'FLM - INTEGRATEL'):
                proyecto = Proyecto.query.filter_by(nombre=nombre).one()
                db.session.add(AccesoProyecto(usuario_id=user.id, proyecto_id=proyecto.id, restricciones='{}'))
            db.session.commit()
            uid = user.id
        with cuenta.session_transaction() as ses:
            ses.update(user_id=uid, username=f'qa-ab-{rol}', rol=rol, form_csrf='gestion-csrf')
        return cuenta

    gestora = operador('gestor')
    parque = operador('supervisor')
    with app.app_context():
        for modulo, clave, contenido in (
            ('Generadores', 'QA-GEP-CATALOGO', {'QR ASIGNADO': 'QA-AB-01', 'SERIE DE EQUIPO': '0001',
                                                'PROYECTO': 'FLM - INTEGRATEL'}),
            ('Generadores', 'QA-GEP-LEGADO', {'QR ASIGNADO': 'QA-GEP-SIN-PROYECTO', 'ZONA': 'ICA'}),
            ('FLM - INTEGRATEL', 'CM-20261124-00000028', {}),
            ('FLM - INTEGRATEL', 'PLM-20261124-00000038', {}),
            ('FLM - CLARO', 'CM-20261124-00000048', {}),
            ('SITE', 'QA-SITE-AB', {'Nombre del sitio | Site name': 'CHOQUECANCHA QA',
                                  'Código del sitio | Site ID': 'HU-ABC', 'Proyecto': 'FLM - INTEGRATEL'}),
        ):
            pid = Proyecto.query.filter_by(nombre=modulo).one().id
            db.session.add(NucleusData(proyecto_id=pid, key_value=clave, data_json=json.dumps(contenido)))
        db.session.commit()
    assert gestora.get('/abastecimiento/').status_code == 200
    assert parque.get('/abastecimiento/?estado=parque').status_code == 200
    inicio = mobile.get('/form-pruebas/abastecimiento').get_data(as_text=True)
    assert all(f'seccion={seccion}' in inicio for seccion in ('solicitar', 'bandeja'))
    assert 'Galones solicitados' not in inicio and 'Mis pedidos' not in inicio
    portal = mobile.get('/form-pruebas/abastecimiento?seccion=solicitar').get_data(as_text=True)
    assert 'value="Técnico QA" readonly' in portal and 'value="FLM - INTEGRATEL" readonly' in portal
    assert all(f'>{grifo}</option>' in portal for grifo in ('Primax', 'Redcol', 'Otro'))
    inventario = mobile.get('/form-pruebas/abastecimiento/catalogos').json['generadores']
    assert any(g['qr'] == 'QA-AB-01' for g in inventario)
    assert not any(g['qr'] == 'QA-GEP-SIN-PROYECTO' for g in inventario)
    url_catalogo = '/abastecimiento/catalogos?proyecto=INTEGRATEL&prueba=1'
    assert any(g['qr'] == 'QA-GEP-SIN-PROYECTO' for g in auth_client.get(url_catalogo).json['generadores'])
    assert not any(g['qr'] == 'QA-GEP-SIN-PROYECTO' for g in gestora.get(url_catalogo).json['generadores'])
    assert mobile.get('/form-pruebas/abastecimiento/catalogos?q=HU-ABC').json['sites'][0]['nombre'] == 'CHOQUECANCHA QA'
    assert mobile.get('/form-pruebas/abastecimiento/catalogos?ticket=CM&q=20261124').json['tickets'] == ['CM-20261124-00000028']
    assert gestora.get(url_catalogo + '&ticket=PLM&q=00000038').json['tickets'] == ['PLM-20261124-00000038']
    datos = {'fecha': '2026-11-24', 'zona': 'HUANCAVELICA', 'site': 'QA-SITE-SIN-REGISTRO-761893',
             'cm': 'CM-20261124-00000018', 'plm': 'PLM-20261124-00000018', 'tipo': 'generador',
             'generador': 'QA-AB-01', 'combustible': 'diesel', 'galones': '10'}

    def foto():
        archivo = io.BytesIO()
        Image.new('RGB', (32, 32), 'white').save(archivo, 'PNG')
        archivo.seek(0)
        return archivo, 'imagen.png'

    def post_mobile(ruta, campos):
        return mobile.post('/form-pruebas/abastecimiento/' + ruta, data=campos,
                           headers={'X-CSRF-Token': 'tecnico-csrf', 'X-Ubicacion': '-12,-77,10'})

    def revisar(cuenta, sid, accion, campos):
        return cuenta.post(f'/abastecimiento/{sid}/{accion}', data=campos,
                           headers={'X-CSRF-Token': 'gestion-csrf'})

    assert post_mobile('solicitar', {**datos, 'plm': 'CM-20261124-00000018'}).status_code == 400
    assert post_mobile('solicitar', {**datos, 'generador': 'INVENTADO'}).status_code == 400
    assert post_mobile('solicitar', {**datos, 'galones': '1.15'}).status_code == 400
    assert post_mobile('solicitar', {**datos, 'grifo': 'otro'}).status_code == 400
    sin_referencias = {**datos, 'cm': '', 'plm': '', 'grifo': 'primax'}
    creado = post_mobile('solicitar', sin_referencias)
    assert creado.status_code == 200, creado.json
    sid = creado.json['id']
    validacion = gestora.get('/abastecimiento/').get_data(as_text=True)
    assert 'Tabla de pedidos de abastecimiento' in validacion
    assert f'data-ab-detalle="ab-pedido-{sid}"' in validacion and '<td>Primax</td>' in validacion
    assert post_mobile('solicitar', datos).status_code == 400
    assert revisar(parque, sid, 'validar', datos).status_code == 400
    assert b'Site por verificar' in gestora.get('/abastecimiento/').data
    corregido = {**sin_referencias, 'site': 'HU-ABC', 'grifo': 'otro', 'grifo_otro': 'Estación QA'}
    assert revisar(gestora, sid, 'editar', corregido).status_code == 200
    assert b'Site por verificar' not in gestora.get('/abastecimiento/').data
    assert revisar(gestora, sid, 'validar', corregido).status_code == 200
    generacion = parque.get('/abastecimiento/?estado=parque').get_data(as_text=True)
    assert 'CHOQUECANCHA QA' in generacion and '<td>Estación QA</td>' in generacion
    assert revisar(gestora, sid, 'enviar', {'qr': foto()}).status_code == 400
    assert revisar(parque, sid, 'enviar', {'qr': foto()}).status_code == 200
    assert post_mobile(f'{sid}/referencias', {'cm': datos['cm']}).status_code == 200
    assert b'Tienes un QR listo' in mobile.get('/form-pruebas/').data
    assert f'/{sid}/foto/qr'.encode() in mobile.get('/form-pruebas/abastecimiento?seccion=bandeja').data
    portal_qr = mobile.get('/form-pruebas/abastecimiento?seccion=bandeja').get_data(as_text=True)
    assert 'Mostrar QR a pantalla completa' in portal_qr and 'Cerrar QR' in portal_qr
    assert portal_qr.count('capture="environment"') == 3
    assert mobile.get(f'/form-pruebas/abastecimiento/{sid}/foto/qr').mimetype == 'image/png'
    otro = app.test_client()
    with otro.session_transaction() as ses:
        ses.update(form_documento='81234567', form_personal_id=100010, form_login_at=time.time())
    assert otro.get(f'/form-pruebas/abastecimiento/{sid}/foto/qr').status_code == 404
    assert auth_client.get(f'/abastecimiento/{sid}/foto/qr').status_code == 200
    fotos_llenado = ('boleta', 'antes_llenado', 'despues_llenado')
    assert post_mobile(f'{sid}/llenado', {'cargado': '10', 'boleta': foto()}).status_code == 400
    assert post_mobile(f'{sid}/llenado', {'cargado': '10', **{k: foto() for k in fotos_llenado}}).status_code == 200
    pendiente = post_mobile(f'{sid}/recarga', {'consumido': '7'})
    assert pendiente.status_code == 400 and 'Completa PLM' in pendiente.json['error']
    assert post_mobile(f'{sid}/referencias', {'plm': datos['plm']}).status_code == 200
    assert post_mobile(f'{sid}/recarga', {'consumido': '11'}).status_code == 400
    fotos_recarga = {'antes_recarga': foto(), 'despues_recarga': foto()}
    assert post_mobile(f'{sid}/recarga', {'consumido': '7', **fotos_recarga}).status_code == 200
    assert post_mobile(f'{sid}/referencias', {'cm': datos['cm']}).status_code == 400
    siguiente = {**datos, 'galones': '5.1', 'combustible': 'petroleo'}
    segundo = post_mobile('solicitar', siguiente).json['id']
    assert revisar(gestora, segundo, 'validar', siguiente).status_code == 200
    with app.app_context():
        assert db.session.get(AbastecimientoSolicitud, sid).saldo_final == 3
        sol = db.session.get(AbastecimientoSolicitud, segundo)
        assert (sol.saldo_previo, sol.autorizado, sol.estado) == (3, Decimal('2.1'), 'parque')

    assert revisar(parque, segundo, 'enviar', {'qr': foto()}).status_code == 200
    assert post_mobile(f'{segundo}/llenado', {'cargado': '3'}).status_code == 400
    assert post_mobile(f'{segundo}/llenado', {'cargado': '2', **{k: foto() for k in fotos_llenado}}).status_code == 200
    assert post_mobile(f'{segundo}/recarga', {'consumido': '2', 'antes_recarga': foto(), 'despues_recarga': foto()}).status_code == 200
    tercero = post_mobile('solicitar', {**datos, 'galones': '3'}).json['id']
    assert revisar(gestora, tercero, 'validar', {**datos, 'galones': '3'}).status_code == 200
    assert revisar(parque, tercero, 'enviar', {}).status_code == 200
    with app.app_context():
        sol = db.session.get(AbastecimientoSolicitud, tercero)
        assert (sol.saldo_previo, sol.autorizado, sol.estado) == (3, 0, 'recarga')
    recarga = auth_client.get('/abastecimiento/?estado=recarga').get_data(as_text=True)
    assert 'Generación QR' in recarga
    assert f'Pedido #{sid}' in recarga and 'Recarga completada' in recarga
    assert f'/{sid}/foto/despues_recarga' in recarga
    assert f'Pedido #{tercero}' in recarga and 'Pendiente de evidencia' in recarga
    assert '?estado=cerrado' not in recarga

    prueba = auth_client.get('/abastecimiento/prueba/')
    assert prueba.status_code == 200 and b'Modo de prueba' in prueba.data
    assert b'TOTAL POR RENDIR' in prueba.data and b'/abastecimiento/prueba/pedidos' in prueba.data
    with auth_client.session_transaction() as ses:
        csrf_admin = ses['form_csrf']
    headers = {'X-CSRF-Token': csrf_admin}
    legado = {**datos, 'proyecto': 'INTEGRATEL', 'generador': 'QA-GEP-SIN-PROYECTO'}
    respuesta = auth_client.post('/abastecimiento/prueba/solicitar', data=legado, headers=headers)
    assert respuesta.status_code == 200, respuesta.json
    creado = auth_client.post('/abastecimiento/prueba/solicitar',
                              data={**datos, 'proyecto': 'INTEGRATEL'}, headers=headers)
    assert creado.status_code == 200, creado.json
    piloto = creado.json['id']
    assert b'PRUEBA' in auth_client.get('/abastecimiento/').data
    assert revisar(gestora, piloto, 'validar', datos).status_code == 200
    with app.app_context():
        sol = db.session.get(AbastecimientoSolicitud, piloto)
        assert sol.tecnico_id < 0 and sol.unidad.startswith('prueba:')
        assert (sol.saldo_previo, sol.autorizado) == (0, 10)
    assert revisar(parque, piloto, 'enviar', {'qr': foto()}).status_code == 200
    assert f'/{piloto}/foto/qr'.encode() in auth_client.get('/abastecimiento/prueba/pedidos?seccion=bandeja').data
    assert auth_client.post(f'/abastecimiento/prueba/{piloto}/llenado', headers=headers,
                            data={'cargado': '10', **{k: foto() for k in fotos_llenado}}).status_code == 200
    assert auth_client.post(f'/abastecimiento/prueba/{piloto}/recarga', headers=headers,
                            data={'consumido': '7', 'antes_recarga': foto(), 'despues_recarga': foto()}).status_code == 200
    assert gestora.get('/abastecimiento/prueba/').status_code == 403
