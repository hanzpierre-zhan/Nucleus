"""Caja Chica: portal del técnico (/form-pruebas/caja-chica) y gestión (/caja-chica)."""
import io
import json
import mimetypes
import re
from collections import defaultdict
from decimal import Decimal

from flask import (Blueprint, Response, abort, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from sqlalchemy.orm import selectinload

from db import db
from models import AppConfig, CajaChicaItem, CajaChicaSolicitud, NucleusData, Proyecto
from services import audit_user, get_menu_proyectos, login_required
from services import caja_chica as cc
from services.formularios_prueba import importe
from services.recursos_flm import familia
from services.alcance_proyectos import _valor
from services.rendicion_presupuesto_cotizacion import cantidad_items, proyecto as proyecto_cotizacion, suma_valores_unitarios
from blueprints.formularios_prueba import (BANCOS, CATALOGO_GASTOS, PROYECTOS, comprobar_csrf,
                                           csrf, responsables_por_proyecto, tecnico)

bp = Blueprint('caja_chica', __name__)
ROLES_TODO = ('zeno', 'suport', 'admin')
ROLES_ELIMINAR = ('zeno', 'admin')
CLAVE_CATALOGO = 'catalogo_gastos'


def _config_catalogo():
    modulo = Proyecto.query.filter_by(nombre=cc.MODULO).first()
    return modulo, AppConfig.query.filter_by(proyecto_id=modulo.id, clave=CLAVE_CATALOGO).first() if modulo else None


def _catalogo(config):
    if config:
        return json.loads(config.valor)
    return [
        {'nombre': nombre, 'descripcion': descripcion, 'correo': False, 'cotizacion': False,
         'proyectos': {p: regla.get(p, '') if isinstance(regla, dict) else regla for p in PROYECTOS}}
        for _, _, nombre, regla, descripcion in CATALOGO_GASTOS
    ]


def _error(exc):
    return jsonify(error=str(exc)), 400


# ── Portal del técnico ─────────────────────────────────────────────────────

@bp.get('/form-pruebas/caja-chica')
def portal():
    if not session.get('form_documento') or session.get('form_debe_cambiar'):
        return redirect(url_for('form_pruebas.inicio'))
    return render_template('caja_chica_tecnico.html', csrf=csrf(), bancos=BANCOS, proyectos=PROYECTOS)


@bp.get('/form-pruebas/caja-chica/datos')
@tecnico
def portal_datos():
    solicitudes = (CajaChicaSolicitud.query.filter_by(documento=g.tecnico['documento'])
                   .filter(CajaChicaSolicitud.estado.notin_((*cc.ESTADOS_FINALES, 'ELIMINADO')))
                   .options(selectinload(CajaChicaSolicitud.items))
                   .order_by(CajaChicaSolicitud.id.desc()).all())
    return jsonify(personal=g.tecnico, proyecto=familia(g.tecnico['proyecto']), catalogo=_catalogo(_config_catalogo()[1]),
                   responsables=responsables_por_proyecto(),
                   solicitudes=[cc.a_dict(s) for s in solicitudes])


@bp.post('/form-pruebas/caja-chica/solicitar')
@tecnico
def portal_solicitar():
    comprobar_csrf()
    try:
        datos, formulario = _datos_portal()
        sol = cc.crear(g.tecnico, datos, _catalogo(_config_catalogo()[1]), PROYECTOS, BANCOS, importe, formulario)
    except ValueError as exc:
        db.session.rollback()
        return _error(exc)
    return jsonify(success=True, solicitud=cc.a_dict(sol))


@bp.post('/form-pruebas/caja-chica/<int:sid>/reenviar')
@tecnico
def portal_reenviar(sid):
    comprobar_csrf()
    sol = _propia(sid)
    try:
        datos, formulario = _datos_portal()
        cc.reenviar(sol, g.tecnico, datos, _catalogo(_config_catalogo()[1]), PROYECTOS, BANCOS, importe, formulario)
    except ValueError as exc:
        db.session.rollback()
        return _error(exc)
    return jsonify(success=True, solicitud=cc.a_dict(sol))


def _datos_portal():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ValueError('Los datos de la solicitud no son válidos.')
    if not re.fullmatch(r'[0-9]{20}', str(datos.get('cuenta') or '')):
        raise ValueError('Ingresa el CCI de 20 dígitos.')
    proyecto = str(datos.get('proyecto') or '').strip()
    responsables = responsables_por_proyecto().get(proyecto, {}) if datos.get('responsable_validacion') else {}
    return datos, cc.datos_formulario(datos, g.tecnico.get('supervisor', ''), responsables)


def _propia(sid):
    sol = db.session.get(CajaChicaSolicitud, sid)
    if not sol or sol.estado == 'ELIMINADO' or sol.documento != g.tecnico['documento']:
        abort(404)
    return sol


@bp.post('/form-pruebas/caja-chica/<int:sid>/item/<int:iid>/rendir')
@tecnico
def portal_rendir(sid, iid):
    comprobar_csrf()
    sol = _propia(sid)
    item = db.session.get(CajaChicaItem, iid)
    if not item or item.solicitud_id != sol.id:
        abort(404)
    try:
        archivos = [a for a in request.files.getlist('fotos') if a and a.filename][:cc.MAX_FOTOS + 1]
        if len(archivos) > cc.MAX_FOTOS:
            raise ValueError('Adjunta como máximo %d fotos.' % cc.MAX_FOTOS)
        fotos = [cc.guardar_foto(sol, a) for a in archivos]
        cc.rendir_item(sol, item, g.tecnico['documento'], request.form, fotos, importe)
    except ValueError as exc:
        db.session.rollback()
        return _error(exc)
    return jsonify(success=True, solicitud=cc.a_dict(sol))


@bp.post('/form-pruebas/caja-chica/<int:sid>/devolucion')
@tecnico
def portal_devolucion(sid):
    comprobar_csrf()
    sol = _propia(sid)
    try:
        archivo = request.files.get('foto')
        if not archivo or not archivo.filename:
            raise ValueError('Adjunta la foto del depósito de devolución.')
        cc.devolver(sol, g.tecnico['documento'], request.form.get('monto'), cc.guardar_foto(sol, archivo), importe)
    except ValueError as exc:
        db.session.rollback()
        return _error(exc)
    return jsonify(success=True, solicitud=cc.a_dict(sol))


@bp.get('/form-pruebas/caja-chica/foto/<int:sid>/<nombre>')
def foto(sid, nombre):
    """El técnico ve sus fotos; la gestión, las de su alcance."""
    sol = db.session.get(CajaChicaSolicitud, sid)
    if not sol or sol.estado == 'ELIMINADO' or nombre not in cc.fotos_de(sol):
        abort(404)
    if session.get('form_documento'):
        if session['form_documento'] != sol.documento:
            abort(404)
    elif not session.get('user_id') or not _en_alcance(sol, _alcance()):
        abort(404)
    try:
        contenido = cc.leer_foto(sol, nombre)
    except Exception:
        abort(404)
    respuesta = Response(contenido, mimetype=mimetypes.guess_type(nombre)[0] or 'image/jpeg')
    respuesta.headers['Cache-Control'] = 'private, max-age=3600'
    return respuesta


# ── Gestión en Nucleus ─────────────────────────────────────────────────────

def _alcance():
    """None = todos los proyectos; si no, las familias FLM asignadas al usuario."""
    rol = str(session.get('rol') or '').strip().lower()
    menu = get_menu_proyectos(session.get('user_id'), rol)
    if not any(p.nombre == cc.MODULO for p in menu):
        abort(403)
    if rol in ROLES_TODO:
        return None
    return {familia(p.nombre) for p in menu} - {''}


def _en_alcance(sol, alcance):
    return alcance is None or sol.proyecto in alcance


@bp.get('/api/caja-chica/cotizaciones')
@login_required
def gestion_cotizaciones():
    alcance = _alcance()
    acumulados = defaultdict(Decimal)
    solicitud_id = request.args.get('solicitud', type=int)
    if solicitud_id is not None:
        solicitud = db.session.get(CajaChicaSolicitud, solicitud_id)
        if not solicitud or solicitud.estado == 'ELIMINADO' or not _en_alcance(solicitud, alcance):
            abort(404)
        activas = CajaChicaSolicitud.query.filter(
            CajaChicaSolicitud.id != solicitud_id,
            CajaChicaSolicitud.estado.notin_(('ANULADO', 'ELIMINADO', 'RECHAZADO')),
        )
        if alcance is not None:
            activas = activas.filter(CajaChicaSolicitud.proyecto.in_(alcance))
        for total, historial in activas.with_entities(CajaChicaSolicitud.total, CajaChicaSolicitud.historial):
            revision = cc.revision_guardada(json.loads(historial or '[]'))
            codigo = str(revision.get('cotizacion') or '').strip().upper()
            if codigo:
                acumulados[codigo] += total
    modulo = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not modulo:
        return jsonify(cotizaciones=[])
    raw = NucleusData.data_json
    filas = NucleusData.query.filter_by(proyecto_id=modulo.id).with_entities(
        NucleusData.key_value, _valor(raw, 'N° COTIZACION'), _valor(raw, 'ESTADO COTIZACION'),
        _valor(raw, 'ITEMS_JSON'), _valor(raw, 'CLIENTE'), _valor(raw, 'Nombre del proyecto'), _valor(raw, 'PROYECTO'),
    ).order_by(NucleusData.id.desc())
    cotizaciones = []
    for clave, numero, estado, items, cliente, nombre, proyecto in filas:
        familia_cot = proyecto_cotizacion({'CLIENTE': cliente, 'Nombre del proyecto': nombre, 'PROYECTO': proyecto})
        if alcance is not None and familia_cot not in alcance:
            continue
        codigo = str(numero or clave or '').strip()
        if codigo:
            cotizaciones.append({'numero': codigo, 'estado': str(estado or '').strip(), 'proyecto': familia_cot,
                                 'monto': suma_valores_unitarios(items), 'items': cantidad_items(items),
                                 'otras_solicitudes': str(acumulados[codigo.upper()])})
    return jsonify(cotizaciones=cotizaciones)


@bp.get('/caja-chica/')
@login_required
def gestion():
    _alcance()
    return render_template('caja_chica.html',
                           csrf=csrf(),
                           catalogo=_catalogo(_config_catalogo()[1]), bancos=BANCOS, proyectos=PROYECTOS,
                           puede_gestionar=str(session.get('rol') or '').lower() not in ('demo', 'contrata'),
                           puede_eliminar=str(session.get('rol') or '').lower() in ROLES_ELIMINAR,
                           administra_catalogo=session.get('rol', '').lower() in ROLES_TODO,
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')))


@bp.route('/caja-chica/catalogo', methods=['GET', 'POST'])
@login_required
def gestion_catalogo():
    _alcance()
    if str(session.get('rol') or '').strip().lower() not in ROLES_TODO:
        abort(403)
    modulo, config = _config_catalogo()
    if request.method == 'POST':
        comprobar_csrf()
        try:
            catalogo = cc.normalizar_catalogo(request.get_json(silent=True), PROYECTOS)
        except ValueError as exc:
            return _error(exc)
        if not config:
            config = AppConfig(proyecto_id=modulo.id, clave=CLAVE_CATALOGO)
            db.session.add(config)
        config.valor = json.dumps(catalogo, ensure_ascii=False)
        db.session.commit()
        return jsonify(success=True)
    return render_template('caja_chica_catalogo.html', catalogo=_catalogo(config), csrf=csrf(),
                           proyectos=('ENTEL', 'CLARO', 'PEXT', 'INTEGRATEL'),
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')))


@bp.get('/api/caja-chica/solicitudes')
@login_required
def gestion_lista():
    alcance = _alcance()
    consulta = CajaChicaSolicitud.query.filter(CajaChicaSolicitud.estado != 'ELIMINADO').order_by(CajaChicaSolicitud.id.desc())
    if alcance is not None:
        consulta = consulta.filter(CajaChicaSolicitud.proyecto.in_(alcance or {''}))
    return jsonify(solicitudes=[cc.a_dict(s, gestion=True) for s in consulta.limit(1000).all()])


@bp.get('/api/caja-chica/<int:sid>/correo-validacion')
@login_required
def gestion_correo(sid):
    alcance = _alcance()
    sol = db.session.get(CajaChicaSolicitud, sid)
    if not sol or sol.estado == 'ELIMINADO' or not _en_alcance(sol, alcance):
        abort(404)
    nombre = cc.a_dict(sol, gestion=True)['revision'].get('archivo')
    if not nombre:
        abort(404)
    try:
        contenido = cc.leer_foto(sol, nombre)
    except Exception:
        abort(404)
    respuesta = send_file(io.BytesIO(contenido), as_attachment=True, max_age=0,
                          download_name='correo-validacion' + nombre[nombre.rfind('.'):],
                          mimetype='application/octet-stream')
    respuesta.headers['Cache-Control'] = 'private, no-store'
    return respuesta


@bp.post('/api/caja-chica/exportar')
@login_required
def gestion_exportar():
    alcance = _alcance()
    comprobar_csrf()
    ids = request.get_json(silent=True)
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 1000
            or any(type(i) is not int or not 0 < i <= 2147483647 for i in ids)):
        return _error('Selecciona solicitudes válidas para exportar.')
    consulta = (CajaChicaSolicitud.query.filter(CajaChicaSolicitud.id.in_(ids), CajaChicaSolicitud.estado != 'ELIMINADO')
                .options(selectinload(CajaChicaSolicitud.items)))
    if alcance is not None:
        consulta = consulta.filter(CajaChicaSolicitud.proyecto.in_(alcance))
    filas = {s.id: s for s in consulta.all()}
    if set(ids) != filas.keys():
        abort(404)
    archivo = cc.exportar_excel(filas[i] for i in dict.fromkeys(ids))
    return send_file(archivo, as_attachment=True, download_name='Caja-Chica.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.post('/api/caja-chica/<int:sid>/<accion>')
@login_required
def gestion_accion(sid, accion):
    rol = str(session.get('rol') or '').lower()
    if rol in ('demo', 'contrata') or (accion == 'eliminar' and rol not in ROLES_ELIMINAR):
        return jsonify(error='Tu rol no permite gestionar Caja Chica.'), 403
    if accion in ('eliminar', 'editar', 'documentos'):
        comprobar_csrf()
    alcance = _alcance()
    sol = db.session.get(CajaChicaSolicitud, sid)
    if not sol or sol.estado == 'ELIMINADO' or not _en_alcance(sol, alcance):
        abort(404)
    datos = request.form if request.files else (request.get_json(silent=True) or {})
    usuario = audit_user() or 'Desconocido'
    try:
        if accion == 'validar':
            cc.validar(sol, usuario)
        elif accion == 'documentos':
            cc.guardar_documentos_revision(sol, usuario, request.form.get('cotizacion'), request.files.get('correo'))
        elif accion == 'editar':
            try:
                cambios = json.loads(request.form.get('datos', ''))
            except ValueError:
                raise ValueError('Los datos de la solicitud no son válidos.') from None
            if not isinstance(cambios, dict):
                raise ValueError('Los datos de la solicitud no son válidos.')
            if alcance is not None and cambios.get('proyecto') not in alcance:
                abort(403)
            cc.editar_revision(sol, usuario, cambios, request.files.get('correo'),
                               _catalogo(_config_catalogo()[1]), PROYECTOS, BANCOS, importe)
        elif accion == 'eliminar':
            cc.eliminar([sol], usuario)
            return jsonify(success=True)
        elif accion == 'rechazar':
            cc.rechazar(sol, usuario, datos.get('motivo'))
        elif accion == 'anular':
            cc.anular(sol, usuario, datos.get('motivo'))
        elif accion == 'depositar':
            archivo = request.files.get('foto')
            if not archivo or not archivo.filename:
                raise ValueError('Adjunta la foto del depósito.')
            if sol.estado != 'VALIDADO':
                raise ValueError('Solo se deposita una solicitud validada.')
            cc.depositar(sol, usuario, datos.get('fecha'), datos.get('monto'), cc.guardar_foto(sol, archivo), importe)
        elif accion == 'revisar_item':
            item = db.session.get(CajaChicaItem, int(datos.get('item') or 0))
            if not item or item.solicitud_id != sol.id:
                abort(404)
            cc.revisar_item(sol, item, usuario, datos.get('aprobar') is True, datos.get('motivo') or '')
        elif accion == 'devolucion':
            cc.confirmar_devolucion(sol, usuario, datos.get('aceptar') is True, datos.get('motivo') or '')
        else:
            abort(404)
    except ValueError as exc:
        db.session.rollback()
        return _error(exc)
    return jsonify(success=True, solicitud=cc.a_dict(sol, gestion=True))


@bp.post('/api/caja-chica/eliminar')
@login_required
def gestion_eliminar():
    if str(session.get('rol') or '').lower() not in ROLES_ELIMINAR:
        abort(403)
    _alcance()
    comprobar_csrf()
    ids = request.get_json(silent=True)
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 1000
            or any(type(i) is not int or not 0 < i <= 2147483647 for i in ids)):
        return _error('Selecciona solicitudes válidas para eliminar.')
    filas = (CajaChicaSolicitud.query.filter(CajaChicaSolicitud.id.in_(ids),
                                           CajaChicaSolicitud.estado != 'ELIMINADO')
             .order_by(CajaChicaSolicitud.id).with_for_update().all())
    if len(filas) != len(set(ids)):
        abort(404)
    cc.eliminar(filas, audit_user() or 'Desconocido')
    return jsonify(success=True)
