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
import os, json, time, re, tempfile, mimetypes, unicodedata, urllib.request
from urllib.parse import quote
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


# ─────────────────────────────────────────────────────────────────────────────
# Aviso de depósito por WhatsApp: enlace wa.me (gratis, sin API ni cuenta de
# Meta). WhatsApp abre con el mensaje YA ESCRITO y el gestor solo aprieta el
# botón verde de enviar. No se manda solo porque WhatsApp no da envío gratis
# automático: eso exigiría la API de Meta (de pago) o una sesión automatizada
# (que puede hacer que bloqueen el número).
# ─────────────────────────────────────────────────────────────────────────────
def _campo(row, patron):
    """Busca un campo por nombre "normalizado" (sin acentos ni símbolos), para
    no depender de si el dato trae 'N°' o 'Nº' o 'Número'."""
    def norm(s):
        s = unicodedata.normalize('NFKD', str(s or '').lower())
        return re.sub(r'[^a-z0-9]', '', s)
    p = norm(patron)
    for k, v in row.items():
        if norm(k) == p:
            return str(v or '').strip()
    return ''


def _wa_celular(row):
    """Celular válido para WhatsApp, o '' si no hay.

    Primero 'Numero de Yape/Plin' (siempre 9 dígitos) y, si falta, el campo
    'Número de celular o CCI' SOLO cuando trae 9 dígitos: en ese campo también
    llegan CCI bancarios de 20 dígitos, que no sirven como número."""
    for patron in ('numerodeyapeplin', 'numerodecelularocci'):
        d = re.sub(r'\D', '', _campo(row, patron))
        if len(d) == 11 and d.startswith('51'):
            d = d[2:]
        if len(d) == 9 and d.startswith('9'):
            return d
    return ''


def _wa_fecha(v):
    """'2026-10-05T14:30' -> '05/10/2026 14:30'."""
    s = str(v or '').strip()
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?', s)
    if not m:
        return s
    a, mes, dia, hh, mm = m.groups()
    txt = '%s/%s/%s' % (dia, mes, a)
    if hh:
        txt += ' %s:%s' % (hh, mm)
    return txt


def _wa_monto(v):
    """1500.5 -> 'S/ 1,500.50'; '80.00 soles' -> 'S/ 80,00' (formato Perú)."""
    s = str(v or '').strip()
    m = re.search(r'-?\d[\d,]*(?:\.\d+)?', s)
    if not m:
        return s
    try:
        n = float(m.group(0).replace(',', ''))
    except ValueError:
        return s
    txt = '{:,.2f}'.format(n).replace(',', '\x00').replace('.', ',').replace('\x00', '.')
    return 'S/ ' + txt


def _wa_deposito(row):
    """Resumen del depósito como enlace wa.me, o None si no hay celular válido."""
    num = _wa_celular(row)
    if not num:
        return None

    nombre = _campo(row, 'Tecnico beneficiario')
    codigo = str(row.get('CODIGO DEPOSITO') or '').strip()
    motivo = _motivo_de(row)
    if len(motivo) > 140:
        motivo = motivo[:137].rstrip() + '...'
    monto = _wa_monto(row.get('MONTO PAGO') or _monto_de(row))
    fecha = _wa_fecha(row.get('FECHA PAGO'))
    site = _site_de(row)
    ticket = _campo(row, 'N CM PM PLM')

    lineas = ['Hola %s 👋' % (nombre or 'buenos días'),
              'Tu depósito en Rendición fue registrado ✅',
              '',
              'Código: %s' % (codigo or '-')]
    if motivo:
        lineas.append('Motivo: %s' % motivo)
    if monto:
        lineas.append('Monto: %s' % monto)
    if fecha:
        lineas.append('Fecha: %s' % fecha)
    if site:
        lineas.append('Sitio: %s' % site)
    if ticket:
        lineas.append('N° de ticket: %s' % ticket)
    lineas += ['',
               '📌 Recuerda sustentar la solicitud en las próximas 24 horas.',
               'IMPORTANTE: La rendición SOLO se valida con BOLETA o FACTURA.',
               '🚫 ESTE MENSAJE ES SOLO PARA INFORMACIÓN — NO RESPONDAS AQUÍ.',
               '⚠️ NO intentes comunicarte por este chat. Cualquier consulta, comunícate ÚNICAMENTE con tu gestor a través del canal oficial.',
               '',
               'Gracias.']
    texto = '\n'.join(lineas)

    return {'numero': '51' + num, 'texto': texto,
            'url': 'https://wa.me/51%s?text=%s' % (num, quote(texto, safe=''))}


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
        elif accion == 'rebote':
            # Rechazo en Rendición (CON SUSTENTO): vuelve a Evidencia para revisión.
            motivo = str(row.get('OBSERVACIONES') or '').strip()
            _crear_aviso(proy_id, 'devolver',
                         '%s rechazó la solicitud en Rendición — %s vuelve a Evidencia%s'
                         % (usuario, site, (': ' + motivo) if motivo else ''),
                         '#FF3B30', usuario)
        elif accion == 'revertir':
            _crear_aviso(proy_id, 'revertir',
                         '%s revirtió la solicitud — %s ahora %s' % (usuario, site, _estado_de(row)),
                         '#8E8E93', usuario)
        elif accion == 'devolver':
            _crear_aviso(proy_id, 'devolver',
                         '%s devolvió la solicitud — %s vuelve a %s para corregir'
                         % (usuario, site, _estado_de(row)),
                         '#8E8E93', usuario)
    except Exception:
        pass



def _folder(pid, key):
    return os.path.join(BASE_DIR, 'static', 'evidencia', str(pid),
                         secure_filename(str(key)))


def _bajar_foto_form(url):
    """Descarga una imagen del 2.º formulario a un archivo temporal.
    Devuelve (ruta_tmp, extension) o (None, None) si falla."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        ctype = (resp.headers.get('Content-Type') or '').lower()
        if ctype.startswith('image/png'):
            ext = '.png'
        elif ctype.startswith('image/webp'):
            ext = '.webp'
        else:
            ext = '.jpg'
        fd, ruta = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        with open(ruta, 'wb') as fh:
            fh.write(data)
        return ruta, ext
    except Exception:
        return None, None


def _persistir_fotos_form(proy_id, key, row):
    """Copia a B2 (o a la carpeta de evidencias si no hay B2) todas las fotos
    que traen las columnas SUSTENTO_* del 2.º formulario, para que el registro
    no dependa del form (los enlaces de Google Forms pueden caducar).
    Devuelve cuántas fotos se persistieron. Nunca rompe el flujo."""
    guardado_clave = '_SUSTENTO_FOTOS_FORM'
    try:
        prev = {}
        if row.get(guardado_clave):
            try:
                prev = json.loads(str(row.get(guardado_clave)))
            except Exception:
                prev = {}
        # Columnas SUSTENTO_* del form + FOTO PAGO del flujo: copiamos las que
        # sean enlaces externos (http/https). Las nuestras (relativas /api/...)
        # ya viven en B2/evidencias y se ignoran.
        candidatos = []
        vistos = set()
        for k, v in row.items():
            if not str(k).startswith('SUSTENTO_'):
                continue
            val = str(v or '').strip()
            if not (val.startswith('http://') or val.startswith('https://')):
                continue
            if val in vistos:
                continue
            vistos.add(val)
            candidatos.append((k, val))
        vp = str(row.get('FOTO PAGO') or '').strip()
        if vp and (vp.startswith('http://') or vp.startswith('https://')) and vp not in vistos:
            vistos.add(vp)
            candidatos.append(('FOTO PAGO', vp))

        if not candidatos:
            return 0

        folder = _folder(proy_id, key)
        persistidas = 0
        idx = 0
        for col, url in candidatos:
            idx += 1
            saved = prev.get(url)
            if not saved:
                ruta_tmp, ext = _bajar_foto_form(url)
                if not ruta_tmp:
                    continue
                try:
                    try:
                        evidencia_comprimir(ruta_tmp)
                    except Exception:
                        pass
                    nombre = 'sustento_form_%03d%s' % (idx, ext)
                    if evidencia_usa_b2():
                        b2_cliente().upload_file(ruta_tmp,
                                                 current_app.config['B2_BUCKET'],
                                                 f'{key}/{nombre}')
                    else:
                        os.makedirs(folder, exist_ok=True)
                        with open(os.path.join(folder, nombre), 'wb') as fh, \
                             open(ruta_tmp, 'rb') as src:
                            fh.write(src.read())
                    saved = '/api/rendicion/foto/%d/%s/%s?v=%d' % (
                        proy_id, key, nombre, int(time.time()))
                    prev[url] = saved
                finally:
                    if os.path.exists(ruta_tmp):
                        try:
                            os.remove(ruta_tmp)
                        except Exception:
                            pass
            if saved:
                row[col] = saved
                persistidas += 1

        if prev:
            row[guardado_clave] = safe_json_dumps(prev)
        return persistidas
    except Exception:
        return 0


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
    if not key or accion not in ('validar', 'rechazar', 'depositar', 'sustentar', 'revertir', 'devolver'):
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
        'rechazar': ('PENDIENTE', 'VALIDADO', 'DEPOSITADO', 'CON SUSTENTO'),
        'depositar': ('VALIDADO',),
        'sustentar': ('DEPOSITADO', 'CON SUSTENTO'),
        'devolver': ('RECHAZADO',),
    }
    if accion in permitido and estado not in permitido[accion]:
        return jsonify({'error': 'No se puede "%s" una solicitud en estado %s.'
                                % (accion, estado)}), 409

    ahora = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    usuario_actual = session.get('username') or 'Desconocido'

    # Siempre actualizamos quién fue el último en interactuar
    row['INTERACCION'] = usuario_actual

    # Datos del aviso por WhatsApp (solo se llenan al depositar).
    wa_deposito = None

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
        if estado == 'CON SUSTENTO':
            # En Rendición el rechazo NO va a la hoja de Rechazados: devuelve la
            # solicitud a Evidencia (DEPOSITADO) para que el gestor la revise.
            row['ESTADO'] = 'DEPOSITADO'
            row['DEVUELTO POR'] = usuario_actual
            row['FECHA DEVOLUCION'] = ahora
            motivo = str(data.get('observaciones') or '').strip()
            if motivo:
                row['OBSERVACIONES'] = motivo
        else:
            row['ESTADO'] = 'RECHAZADO'
            # De dónde viene el rechazo (para devolver a la hoja anterior) + contador.
            row['RECHAZADO DESDE'] = estado
            try:
                vez = int(str(row.get('VECES RECHAZADO', '') or '0').strip() or 0) + 1
            except (ValueError, TypeError):
                vez = 1
            row['VECES RECHAZADO'] = str(vez)
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
        # Datos del aviso por WhatsApp (celular + mensaje con el código).
        wa_deposito = _wa_deposito(row)

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
        # Al quedar en Cerrado, las fotos del 2.º formulario se copian a
        # B2/evidencias para que el registro no dependa del form.
        _persistir_fotos_form(proy.id, key, row)

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

    elif accion == 'devolver':
        # Rechazo con corrección: la solicitud rechazada vuelve a la hoja ANTERIOR
        # (según de dónde vino) para que se corrijan los datos y el flujo avance.
        # Los rechazos hechos en Validación (PENDIENTE) son definitivos.
        est = str(row.get('ESTADO', '')).strip().upper()
        if est != 'RECHAZADO':
            return jsonify({'error': 'Solo se puede devolver una solicitud rechazada.'}), 409
        fuente = str(row.get('RECHAZADO DESDE', '') or '').strip().upper() or 'PENDIENTE'
        destino = {'VALIDADO': 'PENDIENTE',
                   'DEPOSITADO': 'VALIDADO',
                   'CON SUSTENTO': 'DEPOSITADO'}.get(fuente)
        if not destino:
            return jsonify({'error': 'Este rechazo es definitivo y no puede devolverse al flujo.'}), 400
        row['ESTADO'] = destino
        row['DEVUELTO POR'] = usuario_actual
        row['FECHA DEVOLUCION'] = ahora


    fila.data_json = safe_json_dumps(row)
    fila.key_value = key
    db.session.commit()
    # Aviso para todos los que tengan el módulo ("Jessica depositó S/ 100 ...")
    _aviso = 'rebote' if (accion == 'rechazar' and row.get('ESTADO') == 'DEPOSITADO') else accion
    _avisar_flujo(proy.id, _aviso, row, usuario_actual)
    respuesta = {'success': True, 'estado': row['ESTADO'], 'newData': row}
    if wa_deposito:
        respuesta['wa'] = wa_deposito
    return jsonify(respuesta)


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
