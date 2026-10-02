# -*- coding: utf-8 -*-
"""Flujo de Rendicion: pestanas por estado + acciones (validar / rechazar /
   depositar / sustentar) y subida de fotos (comprobante de pago y sustento).

   ESTADO es una columna interna: la gestiona el flujo, no se edita a mano.
   - '' / PENDIENTE -> hoja Validacion
   - VALIDADO      -> hoja Depositos
   - DEPOSITADO    -> hoja Evidencia
   - SUSTENTADO    -> hoja Evidencia (completado)
   - RECHAZADO     -> hoja Rechazados
"""
import os, json, time, tempfile, mimetypes
from datetime import datetime

from flask import (Blueprint, request, jsonify, session, current_app,
                   Response, send_from_directory)
from werkzeug.utils import secure_filename

from db import db
from models import Proyecto, NucleusData, AppConfig, Notificacion
from services import *

bp = Blueprint('rendicion', __name__)

PROY_NOMBRE = 'Rendicion'
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
ESTADOS = ('PENDIENTE', 'VALIDADO', 'RECHAZADO', 'DEPOSITADO', 'CON SUSTENTO', 'SUSTENTADO')
ROLES_ACCION = ('admin', 'zeno', 'suport', 'supervisor', 'gestor')
MAX_FOTOS_SUSTENTO = 5
SLOTS = ('pago', 'susto_1', 'susto_2', 'susto_3', 'susto_4', 'susto_5')
EXT_OK = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif')
_TABLA_AVISOS_OK = [False]


def _proy():
    return Proyecto.query.filter_by(nombre=PROY_NOMBRE).first()


def _puede_gestionar():
    """Habilitado para cualquier usuario que tenga el módulo Rendicion."""
    return bool(session.get('user_id')
                and puede_rendicion(session.get('user_id'), session.get('rol'),
                                    session.get('current_proyecto_nombre')))


def _estado_de(d):
    return str(d.get('ESTADO', '') or '').strip().upper() or 'PENDIENTE'


# ─────────────────────────────────────────────────────────────────────────────
# Avisos del flujo: se guardan una vez y los ven todos los que tengan el
# módulo Rendicion asignado (campanita de la barra superior).
# ─────────────────────────────────────────────────────────────────────────────
def _site_de(row):
    for c in ('Nombre de site', 'SITE', 'Site', 'Nombre Site'):
        v = str(row.get(c) or '').strip()
        if v:
            return v
    return ''


def _monto_de(row):
    for c in ('Monto total del depósito', 'MONTO PAGO', 'Monto', 'Monto total'):
        v = str(row.get(c) or '').strip()
        if v:
            return v
    return ''


def _motivo_de(row):
    for c in ('Motivo de la solicitud', 'MOTIVO DE LA SOLICITUD',
              'Motivo solicitud', 'MOTIVO'):
        v = str(row.get(c) or '').strip()
        if v:
            return v
    return ''


def _crear_aviso(proy_id, tipo, texto, color, autor):
    """Guarda el aviso (nunca rompe el flujo si falla)."""
    try:
        if not _TABLA_AVISOS_OK[0]:
            Notificacion.__table__.create(db.engine, checkfirst=True)
            _TABLA_AVISOS_OK[0] = True
        db.session.add(Notificacion(
            proyecto_id=proy_id, tipo=tipo, texto=texto, color=color,
            autor=autor, creada_en=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _avisar_flujo(proy_id, accion, row, usuario):
    """Texto del aviso según la acción que se acaba de confirmar."""
    try:
        site = _site_de(row) or 'Solicitud'
        monto = _monto_de(row) or '0'
        codigo = str(row.get('CODIGO DEPOSITO') or '').strip()
        if accion == 'validar':
            # Muestra el Motivo de la solicitud (si no tiene, usa el site)
            detalle = _motivo_de(row) or site
            _crear_aviso(proy_id, 'validar',
                         '%s validó S/ %s para depósito — %s' % (usuario, monto, detalle),
                         '#FF9500', usuario)
        elif accion == 'depositar':
            _crear_aviso(proy_id, 'depositar',
                         '%s depositó S/ %s — código %s (%s)' % (usuario, monto, codigo, site),
                         '#007AFF', usuario)
        elif accion == 'rechazar':
            motivo = str(row.get('OBSERVACIONES') or '').strip()
            _crear_aviso(proy_id, 'rechazar',
                         '%s rechazó la solicitud — %s%s'
                         % (usuario, site, (': ' + motivo) if motivo else ''),
                         '#FF3B30', usuario)
        elif accion == 'sustentar':
            _crear_aviso(proy_id, 'sustentar',
                         '%s sustentó el depósito %s — %s' % (usuario, codigo or '-', site),
                         '#AF52DE', usuario)
        elif accion == 'revertir':
            _crear_aviso(proy_id, 'revertir',
                         '%s revirtió la solicitud — %s ahora %s' % (usuario, site, _estado_de(row)),
                         '#8E8E93', usuario)
    except Exception:
        pass



def _folder(pid, key):
    return os.path.join(BASE_DIR, 'static', 'evidencia', str(pid),
                         secure_filename(str(key)))


# ─────────────────────────────────────────────────────────────────────────────
@bp.route('/api/rendicion/accion', methods=['POST'])
@login_required
def api_rendicion_accion():
    """Mueve la solicitud al siguiente estado del flujo."""
    if not _puede_gestionar():
        return jsonify({'error': 'No tienes permisos para gestionar las rendiciones.'}), 403
    proy = _proy()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404

    data = request.get_json(silent=True) or {}
    key = str(data.get('key') or '').strip()
    accion = str(data.get('accion') or '').strip().lower()
    if not key or accion not in ('validar', 'rechazar', 'depositar', 'sustentar', 'revertir'):
        return jsonify({'error': 'Datos incompletos o acción no válida.'}), 400

    fila = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=key).first()
    if not fila:
        return jsonify({'error': 'La solicitud no existe.'}), 404
    try:
        row = json.loads(fila.data_json or '{}')
    except Exception:
        row = {}

    estado = _estado_de(row)
    # Reglas del flujo: cada acción solo desde la hoja que le corresponde.
    # 'revertir' no usa esta tabla: valida su propio mapa de estados más abajo.
    permitido = {
        'validar': ('PENDIENTE',),
        'rechazar': ('PENDIENTE', 'VALIDADO', 'CON SUSTENTO'),
        'depositar': ('VALIDADO',),
        'sustentar': ('DEPOSITADO', 'CON SUSTENTO'),
    }
    if accion in permitido and estado not in permitido[accion]:
        return jsonify({'error': 'No se puede "%s" una solicitud en estado %s.'
                                % (accion, estado)}), 409

    ahora = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    usuario_actual = session.get('username') or 'Desconocido'

    # Siempre actualizamos quién fue el último en interactuar
    row['INTERACCION'] = usuario_actual

    if accion == 'validar':
        # El modal exige elegir una de las 3 opciones de tiempo de respuesta.
        tiempo = str(data.get('tiempo') or '').strip()
        if tiempo not in ('Menor a 4 horas', 'Mayor a 4 horas', 'No aplica'):
            return jsonify({'error': 'Selecciona una opción de tiempo de respuesta.'}), 400
        row['ESTADO'] = 'VALIDADO'
        row['TIEMPO DE RESPUESTA'] = tiempo
        row['FECHA VALIDACION'] = ahora
        row['VALIDADO POR'] = usuario_actual
        row['OBSERVACIONES'] = str(data.get('observaciones') or row.get('OBSERVACIONES') or '').strip()

    elif accion == 'rechazar':
        row['ESTADO'] = 'RECHAZADO'
        row['FECHA RECHAZO'] = ahora
        row['RECHAZADO POR'] = usuario_actual
        motivo = str(data.get('observaciones') or '').strip()
        if motivo:
            row['OBSERVACIONES'] = motivo

    elif accion == 'depositar':
        fecha_pago = str(data.get('fecha_pago') or '').strip()
        monto = str(data.get('monto_pago') or '').strip()
        foto = str(data.get('foto_pago') or '').strip()
        if not fecha_pago:
            return jsonify({'error': 'Ingresa la fecha de pago.'}), 400
        if not monto:
            return jsonify({'error': 'Ingresa el monto pagado.'}), 400
        if not foto:
            return jsonify({'error': 'Adjunta la captura del comprobante.'}), 400

        # ── Generar código de ticket de depósito (COB-XXXXX) ──────────────────
        seq_cfg = AppConfig.query.filter_by(proyecto_id=proy.id,
                                            clave='rendicion_deposit_seq').first()
        try:
            next_seq = int(seq_cfg.valor) + 1 if seq_cfg else 1
        except (ValueError, TypeError):
            next_seq = 1
        codigo_deposito = 'COB-%05d' % next_seq
        if seq_cfg:
            seq_cfg.valor = str(next_seq)
        else:
            db.session.add(AppConfig(proyecto_id=proy.id,
                                     clave='rendicion_deposit_seq',
                                     valor=str(next_seq)))
        # ─────────────────────────────────────────────────────────────────────

        row['ESTADO'] = 'DEPOSITADO'
        row['CODIGO DEPOSITO'] = codigo_deposito
        row['FECHA PAGO'] = fecha_pago
        row['MONTO PAGO'] = monto
        row['FOTO PAGO'] = foto
        row['DEPOSITADO POR'] = usuario_actual

    elif accion == 'sustentar':
        fotos = data.get('fotos') or []
        if isinstance(fotos, str):
            fotos = json.loads(fotos)
        fotos = [str(f).strip() for f in fotos if str(f).strip()][:MAX_FOTOS_SUSTENTO]
        row['ESTADO'] = 'SUSTENTADO'
        # Las fotos ya no son obligatorias: si no vienen, se conservan las anteriores.
        if fotos:
            row['FOTOS SUSTENTO'] = json.dumps(fotos, ensure_ascii=False)
        row['COMENTARIOS SUSTENTO'] = str(data.get('comentario') or '').strip()
        row['FECHA SUSTENTO'] = ahora
        row['SUSTENTADO POR'] = usuario_actual

    elif accion == 'revertir':
        # Permite retroceder el estado de la solicitud (solo zeno, suport o admin).
        # Nota: la sesión guarda el rol en 'rol' (string), no en 'roles'.
        if (session.get('rol') or '').strip().lower() not in ('zeno', 'suport', 'admin'):
            return jsonify({'error': 'No tienes permisos para revertir estados.'}), 403
        est = str(row.get('ESTADO', '')).strip().upper()
        if est == 'VALIDADO':
            row['ESTADO'] = 'PENDIENTE'
        elif est == 'DEPOSITADO':
            row['ESTADO'] = 'VALIDADO'
        elif est == 'CON SUSTENTO':
            row['ESTADO'] = 'DEPOSITADO'
        elif est == 'SUSTENTADO':
            row['ESTADO'] = 'CON SUSTENTO'
        elif est == 'RECHAZADO':
            row['ESTADO'] = 'PENDIENTE'
        else:
            return jsonify({'error': 'No se puede revertir desde este estado.'}), 400


    fila.data_json = safe_json_dumps(row)
    fila.key_value = key
    db.session.commit()
    # Aviso para todos los que tengan el módulo ("Jessica depositó S/ 100 ...")
    _avisar_flujo(proy.id, accion, row, usuario_actual)
    return jsonify({'success': True, 'estado': row['ESTADO'], 'newData': row})


# ─────────────────────────────────────────────────────────────────────────────
@bp.route('/api/rendicion/subir_foto', methods=['POST'])
@login_required
def api_rendicion_subir_foto():
    """Sube una foto (comprobante de pago o sustento) y devuelve su URL."""
    if not _puede_gestionar():
        return jsonify({'error': 'No tienes permisos para subir fotos.'}), 403
    proy = _proy()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404

    pid = proy.id
    key = (request.form.get('key') or '').strip()
    slot = (request.form.get('slot') or '').strip().lower()
    file = request.files.get('foto')
    if not key or slot not in SLOTS:
        return jsonify({'error': 'Datos incompletos.'}), 400
    if file is None or not file.filename:
        return jsonify({'error': 'No se recibió ningún archivo.'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in EXT_OK:
        return jsonify({'error': 'Formato no permitido. Usa JPG, PNG o WEBP.'}), 400

    key = secure_filename(key)
    nombre = 'rendicion_%s.jpg' % slot
    fd, ruta_tmp = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        file.save(ruta_tmp)
        try:
            evidencia_comprimir(ruta_tmp)
        except Exception:
            pass
        if evidencia_usa_b2():
            # borra la versión anterior del mismo slot
            try:
                pref = f'{key}/rendicion_{slot}'
                b2 = b2_cliente()
                for obj in b2.list_objects_v2(Bucket=current_app.config['B2_BUCKET'],
                                              Prefix=pref).get('Contents', []):
                    b2.delete_object(Bucket=current_app.config['B2_BUCKET'], Key=obj['Key'])
            except Exception:
                pass
            b2_cliente().upload_file(ruta_tmp, current_app.config['B2_BUCKET'],
                                     f'{key}/{nombre}')
        else:
            folder = _folder(pid, key)
            os.makedirs(folder, exist_ok=True)
            for viejo in os.listdir(folder):
                if viejo.startswith('rendicion_%s.' % slot):
                    try:
                        os.remove(os.path.join(folder, viejo))
                    except Exception:
                        pass
            with open(os.path.join(folder, nombre), 'wb') as fh:
                with open(ruta_tmp, 'rb') as src:
                    fh.write(src.read())
        url = '/api/rendicion/foto/%d/%s/%s?v=%d' % (pid, key, nombre, int(time.time()))
        return jsonify({'success': True, 'url': url})
    finally:
        if os.path.exists(ruta_tmp):
            try:
                os.remove(ruta_tmp)
            except Exception:
                pass


@bp.route('/api/rendicion/foto/<int:pid>/<path:key>/<path:nombre>')
@login_required
def api_rendicion_foto(pid, key, nombre):
    if not _puede_gestionar():
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _proy()
    if not proy or int(pid) != int(proy.id):
        return jsonify({'error': 'No encontrado'}), 404
    nombre = os.path.basename(secure_filename(nombre))
    if evidencia_usa_b2():
        try:
            obj = b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'],
                                          Key=f'{key}/{nombre}')
            resp = Response(obj['Body'].read(),
                           mimetype=mimetypes.guess_type(nombre)[0] or 'image/jpeg')
            resp.headers['Cache-Control'] = 'private, max-age=604800, immutable'
            return resp
        except Exception:
            return jsonify({'error': 'No encontrado'}), 404
    folder = _folder(pid, key)
    ruta = os.path.join(folder, nombre)
    if not os.path.exists(ruta):
        return jsonify({'error': 'No encontrado'}), 404
    return send_from_directory(folder, nombre, max_age=604800)


# ─────────────────────────────────────────────────────────────────────────────
@bp.route('/api/rendicion/avisos')
@login_required
def api_rendicion_avisos():
    """Últimos avisos del flujo. Solo para quien tenga el módulo Rendicion."""
    if not _puede_gestionar():
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _proy()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404
    uid = int(session.get('user_id') or 0)
    try:
        if not _TABLA_AVISOS_OK[0]:
            Notificacion.__table__.create(db.engine, checkfirst=True)
            _TABLA_AVISOS_OK[0] = True
        filas = (Notificacion.query.filter_by(proyecto_id=proy.id)
                 .order_by(Notificacion.id.desc()).limit(30).all())
    except Exception:
        return jsonify({'avisos': [], 'no_leidas': 0})
    items = []
    for n in filas:
        leidos = set()
        for x in str(n.leida_por or '').replace(';', ',').split(','):
            x = x.strip()
            if x.isdigit():
                leidos.add(int(x))
        items.append({
            'id': n.id, 'tipo': n.tipo, 'texto': n.texto, 'color': n.color,
            'autor': n.autor, 'creada_en': n.creada_en, 'leida': uid in leidos
        })
    return jsonify({'avisos': items,
                    'no_leidas': sum(1 for i in items if not i['leida'])})


@bp.route('/api/rendicion/avisos/leer', methods=['POST'])
@login_required
def api_rendicion_avisos_leer():
    """Marca como leídos los avisos (todos o solo los indicados)."""
    if not _puede_gestionar():
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _proy()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404
    uid = int(session.get('user_id') or 0)
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    try:
        if not _TABLA_AVISOS_OK[0]:
            Notificacion.__table__.create(db.engine, checkfirst=True)
            _TABLA_AVISOS_OK[0] = True
        q = Notificacion.query.filter_by(proyecto_id=proy.id)
        if isinstance(ids, list) and ids:
            q = q.filter(Notificacion.id.in_([int(i) for i in ids if str(i).isdigit()]))
        for n in q.all():
            leidos = set()
            for x in str(n.leida_por or '').replace(';', ',').split(','):
                x = x.strip()
                if x.isdigit():
                    leidos.add(int(x))
            leidos.add(uid)
            n.leida_por = ','.join(str(x) for x in sorted(leidos))
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'No se pudo marcar como leído.'}), 500
    return jsonify({'success': True})
