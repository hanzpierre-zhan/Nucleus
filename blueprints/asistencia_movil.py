"""Nucleus Mobile · Asistencia: el técnico marca su ingreso con su junior, la placa y una foto con coordenadas."""
import re
import time

from flask import Blueprint, Response, abort, g, jsonify, redirect, render_template, session, url_for, request

from db import db
from models import AsistenciaCuadrilla
from services import asistencia_movil as am
from blueprints.formularios_prueba import comprobar_csrf, csrf, tecnico

bp = Blueprint('asistencia_movil', __name__)

# Acciones del técnico que no exigen ubicación (entrar, cambiar clave, salir).
SIN_UBICACION = {'form_pruebas.ingresar', 'form_pruebas.cambiar_clave', 'form_pruebas.salir'}
EVENTOS = {
    'asistencia_movil.registrar': 'Asistencia', 'asistencia_movil.ubicacion': None,
    'caja_chica.portal_solicitar': 'Solicitud', 'form_pruebas.solicitar': 'Solicitud',
    'caja_chica.portal_reenviar': 'Reenvió solicitud', 'caja_chica.portal_rendir': 'Rendición',
    'form_pruebas.rendir': 'Rendición', 'caja_chica.portal_devolver_item': 'Devolución',
    'caja_chica.portal_devolucion': 'Devolución', 'caja_chica.portal_deshacer_devolucion': 'Corrigió devolución',
}


def _accion_tecnico():
    return (request.method == 'POST' and request.path.startswith('/form-pruebas') and session.get('form_documento')
            and request.endpoint not in SIN_UBICACION)


@bp.before_app_request
def exigir_asistencia_diaria():
    doc = session.get('form_documento')
    endpoint = request.endpoint or ''
    if (not doc or session.get('form_debe_cambiar') or not endpoint
            or not request.path.startswith('/form-pruebas')
            or endpoint.startswith('asistencia_movil.') or endpoint in SIN_UBICACION):
        return None
    if time.time() - session.get('form_login_at', 0) > 8 * 3600:
        session.pop('form_documento', None)
        session.pop('form_personal_id', None)
        return redirect(url_for('form_pruebas.inicio')) if request.method == 'GET' else (
            jsonify(error='Tu sesión venció. Vuelve a ingresar.'), 401)
    if am.de_hoy(doc):
        return None
    destino = url_for('asistencia_movil.pantalla')
    if endpoint in ('form_pruebas.inicio', 'caja_chica.portal'):
        return redirect(destino)
    return jsonify(error='Marca tu asistencia de hoy para continuar.', codigo='ASISTENCIA_REQUERIDA',
                   destino=destino), 428


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
    aviso = am.ultimo_rechazo(session['form_documento'])
    return render_template('asistencia_movil.html', csrf=csrf(), rechazo=aviso)


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
    try:
        registro = am.registrar(g.tecnico, request.form, request.files.get('foto'), request.headers.get('X-Dispositivo'))
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    return jsonify(success=True, registro=am.a_dict(registro))


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
