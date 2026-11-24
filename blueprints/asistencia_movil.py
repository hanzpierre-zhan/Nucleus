"""Nucleus Mobile · Asistencia: el técnico marca su ingreso con su junior, la placa y una foto con coordenadas."""
import re
import time

from flask import Blueprint, Response, abort, current_app, g, jsonify, redirect, render_template, session, url_for, request

from db import db
from models import AsistenciaCuadrilla, NucleusData
from services import asistencia_movil as am
from services import perfil_dataper as perfil
from blueprints.formularios_prueba import comprobar_csrf, csrf, tecnico

bp = Blueprint('asistencia_movil', __name__)

# Acciones del técnico que no exigen ubicación (entrar, cambiar clave, salir).
SIN_UBICACION = {'form_pruebas.ingresar', 'form_pruebas.cambiar_clave', 'form_pruebas.salir',
                 'asistencia_movil.actualizar_dataper', 'asistencia_movil.editar_perfil'}
EVENTOS = {
    'asistencia_movil.registrar': 'Asistencia', 'asistencia_movil.ubicacion': None,
    'caja_chica.portal_solicitar': 'Solicitud', 'form_pruebas.solicitar': 'Solicitud',
    'caja_chica.portal_reenviar': 'Reenvió solicitud', 'caja_chica.portal_rendir': 'Rendición',
    'form_pruebas.rendir': 'Rendición', 'caja_chica.portal_devolver_item': 'Devolución',
    'caja_chica.portal_devolucion': 'Devolución', 'caja_chica.portal_deshacer_devolucion': 'Corrigió devolución',
}
SOLICITUDES_CON_ASISTENCIA = {
    'caja_chica.portal_solicitar': 'caja-chica',
    'form_pruebas.solicitar': 'caja-chica',
    'abastecimiento.solicitar': 'abastecimiento',
}


def _accion_tecnico():
    return (request.method == 'POST' and request.path.startswith('/form-pruebas') and session.get('form_documento')
            and request.endpoint not in SIN_UBICACION)


@bp.before_app_request
def preparar_sesion_movil():
    doc = session.get('form_documento')
    endpoint = request.endpoint or ''
    if (not doc or session.get('form_debe_cambiar') or not endpoint
            or not request.path.startswith('/form-pruebas')
            or endpoint in SIN_UBICACION):
        return None
    if time.time() - session.get('form_login_at', 0) > 8 * 3600:
        session.pop('form_documento', None)
        session.pop('form_personal_id', None)
        return redirect(url_for('form_pruebas.inicio')) if request.method == 'GET' else (
            jsonify(error='Tu sesión venció. Vuelve a ingresar.'), 401)
    datos = perfil.leer(db.session.get(NucleusData, session.get('form_personal_id'))) if session.get('form_personal_id') else {}
    g.perfil_mobile_foto = bool(datos.get('_foto_perfil_mobile'))
    g.perfil_mobile_requiere_asistencia = perfil.requiere_asistencia(datos)
    if session.get('form_verificar_dataper'):
        if datos.get('_perfil_mobile_version') != perfil.VERSION:
            destino = url_for('asistencia_movil.actualizar_dataper')
            if request.method == 'GET':
                return redirect(destino)
            return jsonify(error='Actualiza tus datos en Dataper para continuar.',
                           codigo='DATAPER_REQUERIDO', destino=destino), 428
        session.pop('form_verificar_dataper', None)
    origen = SOLICITUDES_CON_ASISTENCIA.get(endpoint)
    if origen == 'abastecimiento' and not current_app.config.get('ABASTECIMIENTO_MOBILE_ENABLED', False):
        abort(404)
    abriendo_solicitud = endpoint == 'caja_chica.portal' and request.args.get('solicitar') == '1'
    if not (origen or abriendo_solicitud) or not asistencia_pendiente(doc):
        return None
    destino = url_for('asistencia_movil.pantalla', solicitud=origen or 'caja-chica')
    if abriendo_solicitud:
        return redirect(destino)
    return jsonify(error='Marca tu asistencia de hoy antes de solicitar.', codigo='ASISTENCIA_REQUERIDA',
                   destino=destino), 428


def asistencia_pendiente(documento):
    return bool(g.get('perfil_mobile_requiere_asistencia') and not am.de_hoy(documento))


@bp.before_app_request
def exigir_ubicacion():
    """Nucleus Mobile: toda acción del técnico debe llegar con su ubicación del momento."""
    if not _accion_tecnico():
        return None
    g.ubicacion_movil = am.leer_ubicacion(request.headers.get('X-Ubicacion'))
    if not g.ubicacion_movil:
        return jsonify(error='Activa tu ubicación (GPS) para usar Nucleus Mobile y vuelve a intentar.', codigo='UBICACION'), 428
    return None


@bp.after_app_request
def guardar_punto(respuesta):
    ubicacion = g.pop('ubicacion_movil', None)
    if ubicacion and respuesta.status_code < 400 and _accion_tecnico():
        evento = EVENTOS.get(request.endpoint, 'Acción en Mobile')
        if request.endpoint == 'asistencia_movil.ubicacion':
            evento = str((request.get_json(silent=True) or {}).get('evento') or 'Abrió Nucleus')[:60]
        try:
            am.guardar_punto(session['form_documento'], ubicacion, evento, request.headers.get('X-Dispositivo'))
        except Exception:
            db.session.rollback()
    return respuesta


@bp.get('/form-pruebas/asistencia')
def pantalla():
    if not session.get('form_documento') or session.get('form_debe_cambiar'):
        return redirect(url_for('form_pruebas.inicio'))
    if not g.perfil_mobile_requiere_asistencia:
        return redirect(url_for('form_pruebas.inicio'))
    aviso = am.ultimo_rechazo(session['form_documento'])
    origen = request.args.get('solicitud')
    continuar = {
        'caja-chica': url_for('caja_chica.portal', solicitar=1, _anchor='nueva'),
        'abastecimiento': url_for('abastecimiento.entrada'),
    }.get(origen)
    return render_template('asistencia_movil.html', csrf=csrf(), rechazo=aviso, continuar_solicitud=continuar)


@bp.get('/form-pruebas/asistencia/datos')
@tecnico
def datos():
    hoy = am.de_hoy(g.tecnico['documento'])
    return jsonify(personal=am.ficha(g.tecnico), juniors=am.juniors(g.tecnico), hoy=am.a_dict(hoy) if hoy else None)


@bp.get('/form-pruebas/asistencia/estado')
@tecnico
def estado():
    hoy = am.de_hoy(g.tecnico['documento'])
    return jsonify(marcado=bool(hoy), hora=hoy.registrado_en.strftime('%H:%M') if hoy else '',
                   rechazo=am.ultimo_rechazo(g.tecnico['documento']))


@bp.post('/form-pruebas/asistencia')
@tecnico
def registrar():
    comprobar_csrf()
    if not g.perfil_mobile_requiere_asistencia:
        return jsonify(error='Tu cargo está exento de marcar asistencia.'), 403
    try:
        registro = am.registrar(g.tecnico, request.form, request.files.get('foto'), request.headers.get('X-Dispositivo'))
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    return jsonify(success=True, registro=am.a_dict(registro))


@bp.route('/form-pruebas/perfil', methods=['GET', 'POST'], endpoint='editar_perfil')
@bp.route('/form-pruebas/dataper', methods=['GET', 'POST'])
@tecnico
def actualizar_dataper():
    fila = db.session.get(NucleusData, g.tecnico['id'], with_for_update=request.method == 'POST')
    datos = perfil.leer(fila)
    editando = request.endpoint == 'asistencia_movil.editar_perfil'
    if not editando and datos.get('_perfil_mobile_version') == perfil.VERSION:
        return redirect(url_for('form_pruebas.inicio'))
    opciones = perfil.opciones(datos)
    valores = perfil.valores(datos)
    error = ''
    if request.method == 'POST':
        comprobar_csrf()
        valores = {campo: request.form.get(campo, '') for campo in perfil.CAMPOS}
        try:
            perfil.guardar(fila, valores, opciones, request.files.get('foto'))
        except ValueError as exc:
            error = str(exc)
        else:
            return redirect(url_for('form_pruebas.inicio'))
    return render_template('perfil_dataper.html', csrf=csrf(), campos=perfil.CAMPOS,
                           valores=valores, opciones=opciones, requeridos=perfil.REQUERIDOS,
                           proyecto=g.tecnico['proyecto'], hoy=am.ahora_peru().date().isoformat(),
                           error=error, editando=editando, tiene_foto=bool(datos.get('_foto_perfil_mobile'))), (400 if error else 200)


@bp.get('/form-pruebas/dataper/foto')
@tecnico
def foto_perfil():
    datos = perfil.leer(db.session.get(NucleusData, g.tecnico['id']))
    nombre = datos.get('_foto_perfil_mobile', '')
    if not re.fullmatch(r'perfil/[a-f0-9]{32}\.jpg', nombre):
        abort(404)
    try:
        contenido = am.leer_foto(nombre)
    except Exception:
        abort(404)
    return Response(contenido, mimetype='image/jpeg', headers={'Cache-Control': 'no-store, private'})


@bp.post('/form-pruebas/ubicacion')
@tecnico
def ubicacion():
    """Punto del recorrido al abrir Nucleus Mobile (lo guarda guardar_punto)."""
    comprobar_csrf()
    return jsonify(success=True)


@bp.get('/form-pruebas/asistencia/foto/<int:rid>')
def foto(rid):
    """El técnico ve su foto (o la de su cuadrilla); la gestión de Nucleus, todas."""
    registro = db.session.get(AsistenciaCuadrilla, rid)
    if not registro or not re.fullmatch(r'\d{4}-\d{2}/[a-f0-9]{32}\.jpg', registro.foto):
        abort(404)
    doc = session.get('form_documento')
    if doc:
        if doc not in (registro.documento, registro.junior_documento):
            abort(404)
    elif not session.get('user_id'):
        abort(404)
    try:
        contenido = am.leer_foto(registro.foto)
    except Exception:
        abort(404)
    respuesta = Response(contenido, mimetype='image/jpeg')
    respuesta.headers['Cache-Control'] = 'private, max-age=3600'
    return respuesta
