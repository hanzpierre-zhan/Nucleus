import io
import time

from PIL import Image

from blueprints import asistencia_movil, formularios_prueba
from db import db
from models import AbastecimientoSolicitud, AccesoProyecto, Proyecto, Usuario


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
    assert gestora.get('/abastecimiento/').status_code == 200
    assert parque.get('/abastecimiento/?estado=parque').status_code == 200
    assert mobile.get('/form-pruebas/abastecimiento').status_code == 200
    datos = {'fecha': '2026-11-24', 'zona': 'HUANCAVELICA', 'site': 'CHOQUECANCHA',
             'cm': 'CM-1', 'plm': 'PLM-1', 'trabajo': 'Recarga', 'tipo': 'generador',
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

    assert post_mobile('solicitar', {**datos, 'cm': ''}).status_code == 400
    assert post_mobile('solicitar', {**datos, 'plm': ''}).status_code == 400
    creado = post_mobile('solicitar', datos)
    assert creado.status_code == 200, creado.json
    sid = creado.json['id']
    assert post_mobile('solicitar', datos).status_code == 400
    assert revisar(parque, sid, 'validar', datos).status_code == 400
    assert revisar(gestora, sid, 'editar', {**datos, 'grifo': 'GRIFO QA'}).status_code == 200
    assert revisar(gestora, sid, 'validar', {**datos, 'grifo': 'GRIFO QA'}).status_code == 200
    assert b'GRIFO QA' in parque.get('/abastecimiento/?estado=parque').data
    assert revisar(gestora, sid, 'enviar', {'qr': foto()}).status_code == 400
    assert revisar(parque, sid, 'enviar', {'qr': foto()}).status_code == 200
    assert b'Tienes un QR listo' in mobile.get('/form-pruebas/').data
    assert f'/{sid}/foto/qr'.encode() in mobile.get('/form-pruebas/abastecimiento').data
    assert mobile.get(f'/form-pruebas/abastecimiento/{sid}/foto/qr').mimetype == 'image/png'
    otro = app.test_client()
    with otro.session_transaction() as ses:
        ses.update(form_documento='81234567', form_personal_id=100010, form_login_at=time.time())
    assert otro.get(f'/form-pruebas/abastecimiento/{sid}/foto/qr').status_code == 404
    assert auth_client.get(f'/abastecimiento/{sid}/foto/qr').status_code == 200
    fotos_llenado = ('boleta', 'antes_llenado', 'despues_llenado')
    assert post_mobile(f'{sid}/llenado', {'cargado': '10', 'boleta': foto()}).status_code == 400
    assert post_mobile(f'{sid}/llenado', {'cargado': '10', **{k: foto() for k in fotos_llenado}}).status_code == 200
    assert post_mobile(f'{sid}/recarga', {'consumido': '11'}).status_code == 400
    fotos_recarga = {'antes_recarga': foto(), 'despues_recarga': foto()}
    assert post_mobile(f'{sid}/recarga', {'consumido': '7', **fotos_recarga}).status_code == 200
    siguiente = {**datos, 'galones': '5'}
    segundo = post_mobile('solicitar', siguiente).json['id']
    assert revisar(gestora, segundo, 'validar', siguiente).status_code == 200
    with app.app_context():
        assert db.session.get(AbastecimientoSolicitud, sid).saldo_final == 3
        sol = db.session.get(AbastecimientoSolicitud, segundo)
        assert (sol.saldo_previo, sol.autorizado, sol.estado) == (3, 2, 'parque')

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
    with auth_client.session_transaction() as ses:
        csrf_admin = ses['form_csrf']
    headers = {'X-CSRF-Token': csrf_admin}
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
    assert f'/{piloto}/foto/qr'.encode() in auth_client.get('/abastecimiento/prueba/').data
    assert auth_client.post(f'/abastecimiento/prueba/{piloto}/llenado', headers=headers,
                            data={'cargado': '10', **{k: foto() for k in fotos_llenado}}).status_code == 200
    assert auth_client.post(f'/abastecimiento/prueba/{piloto}/recarga', headers=headers,
                            data={'consumido': '7', 'antes_recarga': foto(), 'despues_recarga': foto()}).status_code == 200
    assert gestora.get('/abastecimiento/prueba/').status_code == 403
