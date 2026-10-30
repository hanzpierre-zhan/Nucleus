from services.rendicion_estados import estado_de as _estado_de, etapa_de as _etapa_de
# -*- coding: utf-8 -*-
"""Flujo de Rendicion: pestanas por estado + acciones (validar / rechazar /
   depositar / sustentar) y subida de fotos (comprobante de pago y sustento).

   ESTADO es una columna interna: la gestiona el flujo, no se edita a mano.
   - '' / PENDIENTE -> hoja Validacion
   - VALIDADO      -> hoja Depositos
   - DEPOSITADO    -> hoja Evidencia
   - CON SUSTENTO -> hoja Sustento
   - SUBESTADO OBSERVADO -> hoja Observado, conserva el estado principal
   - SUSTENTADO   -> hoja Atendido
   - SUBESTADO ARCHIVADO -> hoja Archivar, conserva SUSTENTADO (Atendido)
   - RECHAZADO    -> Validación o Evidencia según la etapa de retorno
   - ANULADO      -> hoja Anulado (conserva los registros)
"""
import os, json, time, re, csv, io, tempfile, mimetypes, unicodedata, urllib.request
from uuid import uuid4
from urllib.parse import quote
from datetime import datetime

from flask import (Blueprint, request, jsonify, session, current_app,
                   Response, send_from_directory, send_file)
from werkzeug.utils import secure_filename

from db import db
from models import Proyecto, NucleusData, AppConfig, Notificacion, RendicionCorreo
from services.apoyo import guardar_archivo_atomico, comprobar_error_b2
from services import (
    login_required,
    safe_json_dumps,
    audit_user,
    get_menu_proyectos,
    puede_rendicion,
    evidencia_comprimir,
    evidencia_usa_b2,
    b2_cliente,
)

bp = Blueprint('rendicion', __name__)

PROY_NOMBRE = 'Rendicion'
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
ESTADOS = ('PENDIENTE', 'VALIDADO', 'RECHAZADO', 'ANULADO', 'DEPOSITADO', 'CON SUSTENTO', 'OBSERVADO', 'SUSTENTADO', 'ARCHIVADO')
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

    nombre = _campo(row, 'Tecnico beneficiario (Form)') or _campo(row, 'Tecnico beneficiario')
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
                         '%s rechazó la solicitud — %s vuelve a %s%s'
                         % (usuario, site, 'Validación' if _etapa_de(row) == 'VALIDACION' else 'Evidencia',
                            (': ' + motivo) if motivo else ''),
                         '#FF3B30', usuario)
        elif accion == 'anular':
            _crear_aviso(proy_id, 'anular', '%s anuló la solicitud — %s: %s' %
                         (usuario, site, row.get('OBSERVACIONES', '')), '#64748B', usuario)
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
        elif accion in ('observar', 'archivar', 'desarchivar'):
            textos = {'observar': 'observó el sustento', 'archivar': 'archivó la solicitud atendida',
                      'desarchivar': 'desarchivó la solicitud y la devolvió a Atendido'}
            motivo = str(row.get('OBSERVACIONES') or '').strip() if accion == 'observar' else ''
            _crear_aviso(proy_id, accion, '%s %s — %s%s' %
                         (usuario, textos[accion], site, (': ' + motivo) if motivo else ''),
                         '#D97706' if accion == 'observar' else '#173E76', usuario)
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
    return os.path.join(current_app.config['EVIDENCIA_DIR'], str(pid),
                         secure_filename(str(key)))


def _bajar_foto_form(url):
    """Descarga una imagen del 2.º formulario a un archivo temporal.
    Devuelve (ruta_tmp, extension) o (None, None) si falla."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(25 * 1024 * 1024 + 1)
        if not data or len(data) > 25 * 1024 * 1024:
            return None, None
        if data.startswith(b'%PDF-'):
            from pypdf import PdfReader
            if not len(PdfReader(io.BytesIO(data)).pages):
                return None, None
            fd, ruta = tempfile.mkstemp(suffix='.pdf')
            os.close(fd)
            with open(ruta, 'wb') as fh:
                fh.write(data)
            return ruta, '.pdf'
        # Drive puede responder HTTP 200 con una página de acceso en lugar
        # de una foto. No guardarla como JPG ni reemplazar el enlace original.
        from PIL import Image
        with Image.open(io.BytesIO(data)) as imagen:
            formato = imagen.format
            imagen.verify()
        if formato == 'PNG':
            ext = '.png'
        elif formato == 'WEBP':
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
                    nombre = 'sustento_form_%s%s' % (uuid4().hex, ext)
                    if evidencia_usa_b2():
                        b2_cliente().upload_file(ruta_tmp,
                                                 current_app.config['B2_BUCKET'],
                                                 f'{secure_filename(str(key))}/{nombre}')
                    else:
                        os.makedirs(folder, exist_ok=True)
                        with open(os.path.join(folder, nombre), 'wb') as fh, \
                             open(ruta_tmp, 'rb') as src:
                            fh.write(src.read())
                    saved = '/api/rendicion/foto/%d/%s/%s?v=%d' % (
                        proy_id, secure_filename(str(key)), nombre, int(time.time()))
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
@bp.route('/api/rendicion/cotizacion', methods=['GET'])
@login_required
def consultar_presupuesto_cotizacion():
    from services.rendicion_presupuesto_cotizacion import catalogo, encontrar, resumen
    if not _puede_gestionar():
        return jsonify(error='No tienes permiso para consultar esta solicitud.'),403
    proy=_proy()
    fila=NucleusData.query.filter_by(proyecto_id=proy.id,key_value=str(request.args.get('key') or '')).first() if proy else None
    if not fila:return jsonify(error='Solicitud no encontrada.'),404
    row=json.loads(fila.data_json or '{}');consulta=str(request.args.get('q') or '').strip()[:100]
    opciones=catalogo(row,consulta)
    result={'opciones':[{'numero':c['numero']} for c in opciones[:20]],'encontrada':False}
    if consulta:
        try:
            cot=encontrar(row,consulta,opciones)
            result.update(encontrada=True,control=resumen(row,fila.key_value,cot,request.args.get('monto')))
        except ValueError as error:result['mensaje']=str(error)
    return jsonify(result)


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
    if not key or accion not in ('validar', 'rechazar', 'anular', 'depositar', 'sustentar', 'revertir', 'devolver', 'observar', 'archivar', 'desarchivar'):
        return jsonify({'error': 'Datos incompletos o acción no válida.'}), 400

    fila = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=key).with_for_update().first()
    if not fila:
        return jsonify({'error': 'La solicitud no existe.'}), 404
    try:
        row = json.loads(fila.data_json or '{}')
    except Exception:
        row = {}


    estado = _estado_de(row)
    etapa = _etapa_de(row)
    subestado_anterior = row.get('SUBESTADO', '')
    estado_accion = {'OBSERVADO': 'OBSERVADO', 'ARCHIVADO': 'ARCHIVADO'}.get(etapa, estado)
    # Reglas del flujo: cada acción solo desde la hoja que le corresponde.
    # 'revertir' no usa esta tabla: valida su propio mapa de estados más abajo.
    permitido = {
        'validar': ('PENDIENTE', 'RECHAZADO'),
        'rechazar': ('VALIDADO', 'CON SUSTENTO', 'OBSERVADO', 'SUSTENTADO'),
        'depositar': ('VALIDADO',),
        'sustentar': ('CON SUSTENTO', 'OBSERVADO'),
        'devolver': ('RECHAZADO',),
        'observar': ('CON SUSTENTO', 'OBSERVADO', 'SUSTENTADO'),
        'archivar': ('SUSTENTADO',),
        'desarchivar': ('ARCHIVADO',),
    }
    if accion in permitido and estado_accion not in permitido[accion]:
        return jsonify({'error': 'No se puede "%s" una solicitud en estado %s.'
                                % (accion, estado)}), 409
    if (accion == 'validar' and etapa != 'VALIDACION') or (
            accion == 'anular' and etapa not in ('VALIDACION', 'EVIDENCIA')) or (
            accion in ('revertir', 'devolver') and etapa == 'ANULADO'):
        return jsonify({'error': 'Esta acción no corresponde a la etapa actual.'}), 409
    if accion == 'revertir' and etapa in ('ARCHIVADO', 'OBSERVADO'):
        return jsonify({'error': 'Resuelve el subestado antes de revertir la solicitud.'}), 400

    ahora = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    usuario_actual = audit_user() or 'Desconocido'

    # Siempre actualizamos quién fue el último en interactuar
    row['INTERACCION'] = usuario_actual

    # Datos del aviso por WhatsApp (solo se llenan al depositar).
    wa_deposito = None

    if accion == 'anular':
        motivo = str(data.get('observaciones') or '').strip()
        if not motivo:
            return jsonify({'error': 'Escribe el motivo de anulación.'}), 400
        row['ESTADO'] = 'ANULADO'
        row['ANULADO DESDE'] = etapa
        row['ANULADO POR'] = usuario_actual
        row['FECHA ANULACION'] = ahora
        row['OBSERVACIONES'] = motivo

    elif accion == 'observar':
        motivo = str(data.get('observaciones') or '').strip()
        if not motivo:
            return jsonify({'error': 'Escribe qué debe corregirse en el sustento.'}), 400
        row['ESTADO'] = estado if estado != 'OBSERVADO' else 'CON SUSTENTO'
        row['SUBESTADO'] = 'OBSERVADO'
        row['OBSERVACIONES'] = motivo
        row['OBSERVADO POR'] = usuario_actual
        row['FECHA OBSERVACION'] = ahora

    elif accion == 'archivar':
        row['ESTADO'] = 'SUSTENTADO'
        row['SUBESTADO'] = 'ARCHIVADO'
        row['ARCHIVADO POR'] = usuario_actual
        row['FECHA ARCHIVO'] = ahora

    elif accion == 'desarchivar':
        row['ESTADO'] = 'SUSTENTADO'
        row['DESARCHIVADO POR'] = usuario_actual
        row['FECHA DESARCHIVO'] = ahora

    elif accion == 'validar':
        tipo_presupuesto = str(row.get('Tipo de presupuesto') or row.get('TIPO DE PRESUPUESTO') or '').strip().upper()
        cotizacion = str(data.get('cotizacion', row.get('N° COTIZACION')) or '').strip()
        if tipo_presupuesto == 'REFACTURABLE' and not cotizacion:
            return jsonify(error='La cotización es obligatoria para solicitudes REFACTURABLES.'), 400
        if tipo_presupuesto == 'REFACTURABLE' and 'cotizacion' not in data:
            data['cotizacion'] = cotizacion
            data.setdefault('presupuesto', row.get('PRESUPUESTO', ''))
        antes_presupuesto={campo:row.get(campo,'') for campo in ('PRESUPUESTO','N° COTIZACION')}
        from services.rendicion_presupuesto_cotizacion import preparar
        try:
            row.update(preparar(row,key,data))
        except ValueError as error:
            return jsonify(error=str(error)),400
        # El modal exige elegir una de las 3 opciones de tiempo de respuesta.
        tiempo = str(data.get('tiempo') or '').strip()
        if tiempo not in ('Menor a 4 horas', 'Mayor a 4 horas', 'No aplica'):
            return jsonify({'error': 'Selecciona una opción de tiempo de respuesta.'}), 400
        if _requiere_correo_validacion(row):
            # La asociación durable prevalece si una edición antigua perdió el enlace del JSON.
            adjunto = RendicionCorreo.query.filter_by(origen_id=fila.id).order_by(RendicionCorreo.id.desc()).first()
            if adjunto:
                row['ADJUNTO CORREO VALIDACION'] = '/api/rendicion/correo/%s/%s' % (fila.id, adjunto.nombre)
                row['NOMBRE CORREO VALIDACION'] = adjunto.nombre_original
            correo = str(row.get('ADJUNTO CORREO VALIDACION') or '')
            prefijo = '/api/rendicion/correo/%s/' % fila.id
            nombre = correo[len(prefijo):] if correo.startswith(prefijo) else ''
            if not nombre or secure_filename(nombre) != nombre or not _correo_existe(fila.id, nombre):
                return jsonify({'error': 'Adjunta el correo .msg para validar esta solicitud.'}), 400
        from models import HistorialCambios
        for campo,anterior in antes_presupuesto.items():
            if str(anterior)!=str(row.get(campo,'')):
                db.session.add(HistorialCambios(proyecto_id=proy.id,usuario_id=session.get('user_id'),
                    username=usuario_actual,key_value=key,campo_modificado=campo,
                    valor_anterior=str(anterior),valor_nuevo=str(row.get(campo,''))))
        row['ESTADO'] = 'VALIDADO'
        row['TIEMPO DE RESPUESTA'] = tiempo
        row['FECHA VALIDACION'] = ahora
        row['VALIDADO POR'] = usuario_actual
        row['OBSERVACIONES'] = str(data.get('observaciones') or row.get('OBSERVACIONES') or '').strip()

    elif accion == 'rechazar':
        motivo = str(data.get('observaciones') or '').strip()
        if not motivo:
            return jsonify({'error': 'Escribe el motivo del rechazo.'}), 400
        row['ESTADO'] = 'RECHAZADO'
        row['_RECHAZO_ETAPA'] = 'VALIDACION' if estado == 'VALIDADO' else 'EVIDENCIA'
        row['RECHAZADO DESDE'] = estado
        row['FECHA RECHAZO'] = ahora
        row['RECHAZADO POR'] = usuario_actual
        row['OBSERVACIONES'] = motivo
        # Columna propia para que el motivo se vea en la tabla (antes vivía solo
        # dentro de OBSERVACIONES, que no es una columna del módulo).
        row['MOTIVO RECHAZO'] = motivo
        try:
            row['VECES RECHAZADO'] = str(int(row.get('VECES RECHAZADO') or 0) + 1)
        except (ValueError, TypeError):
            row['VECES RECHAZADO'] = '1'

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


    if accion not in ('observar', 'archivar'):
        row['SUBESTADO'] = ''
    historial = row.get('_HISTORIAL_FLUJO')
    if not isinstance(historial, list):
        historial = []
    historial.append({'accion': accion, 'desde': estado, 'hasta': row['ESTADO'],
                      'subestado_desde': subestado_anterior, 'subestado_hasta': row.get('SUBESTADO', ''),
                      'usuario': usuario_actual, 'fecha': ahora,
                      'motivo': str(data.get('observaciones') or '').strip()})
    row['_HISTORIAL_FLUJO'] = historial
    fila.data_json = safe_json_dumps(row)
    fila.key_value = key
    db.session.commit()
    # Aviso para todos los que tengan el módulo ("Jessica depositó S/ 100 ...")
    _aviso = 'rebote' if (accion == 'rechazar' and row.get('ESTADO') == 'DEPOSITADO') else accion
    _avisar_flujo(proy.id, _aviso, row, usuario_actual)
    from services.rendicion_personal import presentar_beneficiario_dataper, indice_personal
    respuesta = {'success': True, 'estado': row['ESTADO'], 'newData': presentar_beneficiario_dataper(row,indice_personal(),solo_meta=True)}
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
        try:
            file.save(ruta_tmp)
            try:
                evidencia_comprimir(ruta_tmp)
            except Exception:
                pass
            if evidencia_usa_b2():
                # La sustitución del objeto ocurre al completar la subida.
                # No borrar primero: un fallo de red perdería la foto anterior.
                b2_cliente().upload_file(ruta_tmp, current_app.config['B2_BUCKET'],
                                         f'{key}/{nombre}')
            else:
                folder = _folder(pid, key)
                os.makedirs(folder, exist_ok=True)
                guardar_archivo_atomico(ruta_tmp, os.path.join(folder, nombre))
            url = '/api/rendicion/foto/%d/%s/%s?v=%d' % (pid, key, nombre, int(time.time()))
            return jsonify({'success': True, 'url': url})
        except Exception as e:
            return jsonify({'error': f'Error procesando foto: {str(e)}'}), 500
    finally:
        if os.path.exists(ruta_tmp):
            try:
                os.remove(ruta_tmp)
            except Exception:
                pass


def _claves_foto(key, pid=None):
    """La llave del registro es una fecha ('6/10/2026 14:30:00'), así que las
    URLs viejas pueden traerla cruda o saneada. Se prueban ambas."""
    vistas = []
    for cand in (key, secure_filename(str(key))):
        cand = str(cand or '').strip()
        if cand and cand not in vistas:
            vistas.append(cand)
    if pid is not None:
        # Las copias antiguas del formulario usaban la fecha cruda en B2,
        # pero publicaban una URL saneada. Recuperar la clave del registro
        # (respetando el alcance ORM), sin adivinar el formato de la fecha.
        for (original,) in db.session.query(NucleusData.key_value).filter_by(proyecto_id=pid):
            if secure_filename(str(original)) == secure_filename(str(key)) and original not in vistas:
                vistas.append(original)
    return vistas


@bp.route('/api/rendicion/foto/<int:pid>/<path:key>/<path:nombre>')
@login_required
def api_rendicion_foto(pid, key, nombre):
    from services.alcance_proyectos import comprobar_archivo
    comprobar_archivo(pid, key)
    if not _puede_gestionar():
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _proy()
    if not proy or int(pid) != int(proy.id):
        return jsonify({'error': 'No encontrado'}), 404
    nombre = os.path.basename(secure_filename(nombre))
    claves = _claves_foto(key)
    if evidencia_usa_b2():
        b2 = b2_cliente()
        for cand in claves:
            try:
                obj = b2.get_object(Bucket=current_app.config['B2_BUCKET'],
                                    Key=f'{cand}/{nombre}')
            except Exception as error:
                comprobar_error_b2(error)
                continue
            resp = Response(obj['Body'].read(),
                            mimetype=mimetypes.guess_type(nombre)[0] or 'image/jpeg')
            resp.headers['Cache-Control'] = 'private, max-age=604800, immutable'
            return resp
        # Compatibilidad con copias históricas guardadas bajo la fecha cruda.
        for cand in _claves_foto(key, pid):
            if cand in claves:
                continue
            try:
                obj = b2.get_object(Bucket=current_app.config['B2_BUCKET'], Key=f'{cand}/{nombre}')
            except Exception as error:
                comprobar_error_b2(error)
                continue
            resp = Response(obj['Body'].read(), mimetype=mimetypes.guess_type(nombre)[0] or 'image/jpeg')
            resp.headers['Cache-Control'] = 'private, max-age=604800, immutable'
            return resp
    for cand in claves:
        carpetas = (_folder(pid, cand), os.path.join(BASE_DIR, 'static', 'evidencia', str(pid), secure_filename(str(cand))))
        for folder in dict.fromkeys(carpetas):
            if os.path.isfile(os.path.join(folder, nombre)):
                return send_from_directory(folder, nombre, max_age=604800)
    return jsonify({'error': 'No encontrado'}), 404


# ─────────────────────────────────────────────────────────────────────────────
@bp.route('/api/rendicion/avisos')
@bp.route('/api/cotizacion/avisos')
@login_required
def api_rendicion_avisos():
    """Últimos avisos del flujo. Solo para quien tenga el módulo Rendicion."""
    from blueprints.cotizacion import _cot_puede_gestionar, _cot_proyecto
    cotizacion = request.path.startswith('/api/cotizacion/')
    if not (_cot_puede_gestionar() if cotizacion else _puede_gestionar()):
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _cot_proyecto() if cotizacion else _proy()
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
@bp.route('/api/cotizacion/avisos/leer', methods=['POST'])
@login_required
def api_rendicion_avisos_leer():
    """Marca como leídos los avisos (todos o solo los indicados)."""
    from blueprints.cotizacion import _cot_puede_gestionar, _cot_proyecto
    cotizacion = request.path.startswith('/api/cotizacion/')
    if not (_cot_puede_gestionar() if cotizacion else _puede_gestionar()):
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _cot_proyecto() if cotizacion else _proy()
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



def _requiere_correo_validacion(row):
    def normalizar(valor):
        texto = unicodedata.normalize('NFKD', str(valor or ''))
        return re.sub(r'[^a-z0-9]', '', ''.join(c for c in texto.lower() if not unicodedata.combining(c)))
    campos = {normalizar(campo): valor for campo, valor in row.items()}
    presupuesto = normalizar(campos.get('tipodepresupuesto', campos.get('tipopresupuesto')))
    gasto = str(campos.get('tipodegasto', campos.get('tipogasto')) or '')
    tipos = [normalizar(tipo) for tipo in re.split(r'[,;/|+\n]+', gasto)]
    exentos = {'viatico', 'viaticos', 'peaje', 'peajes', 'hospedaje', 'hospedajes'}
    if tipos and all(tipo in exentos for tipo in tipos):
        return False
    if presupuesto == 'refacturable':
        return True
    if presupuesto != 'gastocobra':
        return False
    return not tipos or any(tipo not in exentos for tipo in tipos)


def _correo_folder(origen_id):
    return os.path.join(current_app.config.get('EVIDENCIA_DIR') or os.path.join(BASE_DIR, 'static', 'evidencia'), 'rendicion_correos', str(origen_id))


def _correo_existe(origen_id, nombre):
    if RendicionCorreo.query.filter_by(origen_id=origen_id, nombre=nombre).first():
        return True
    if os.path.isfile(os.path.join(_correo_folder(origen_id), nombre)):
        return True
    if evidencia_usa_b2():
        try:
            b2_cliente().head_object(Bucket=current_app.config['B2_BUCKET'],
                                    Key=f'rendicion_correos/{origen_id}/{nombre}')
            return True
        except Exception:
            pass
    return False


@bp.route('/api/rendicion/subir_correo', methods=['POST'])
@login_required
def subir_correo_validacion():
    if not _puede_gestionar():
        return jsonify({'error': 'No tienes permisos para gestionar las rendiciones.'}), 403
    proy = _proy()
    key = str(request.form.get('key') or '').strip()
    fila = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=key).with_for_update().first() if proy else None
    if not fila:
        return jsonify({'error': 'Solicitud no encontrada.'}), 404
    row = json.loads(fila.data_json or '{}')
    if _etapa_de(row) != 'VALIDACION' or not _requiere_correo_validacion(row):
        return jsonify({'error': 'Este correo corresponde a una solicitud pendiente que requiere correo de validación.'}), 409
    archivo = request.files.get('correo')
    if not archivo or not archivo.filename or os.path.splitext(archivo.filename)[1].lower() != '.msg':
        return jsonify({'error': 'Selecciona un correo de Outlook en formato .msg.'}), 400
    contenido = archivo.read(20 * 1024 * 1024 + 1)
    if not contenido or len(contenido) > 20 * 1024 * 1024:
        return jsonify({'error': 'El correo debe tener contenido y pesar como máximo 20 MB.'}), 400
    carpeta = _correo_folder(fila.id)
    os.makedirs(carpeta, exist_ok=True)
    nombre = uuid4().hex + '.msg'
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, 'wb') as destino:
        destino.write(contenido)
    if evidencia_usa_b2():
        try:
            b2_cliente().upload_file(ruta, current_app.config['B2_BUCKET'],
                                     f'rendicion_correos/{fila.id}/{nombre}')
        except Exception:
            os.remove(ruta)
            current_app.logger.exception('No se pudo persistir el correo de validación en B2')
            return jsonify({'error': 'No se pudo guardar el correo. Reintenta la subida.'}), 503
    row['ADJUNTO CORREO VALIDACION'] = '/api/rendicion/correo/%s/%s' % (fila.id, nombre)
    row['NOMBRE CORREO VALIDACION'] = secure_filename(archivo.filename)
    db.session.add(RendicionCorreo(origen_id=fila.id, nombre=nombre,
                                  nombre_original=row['NOMBRE CORREO VALIDACION'], contenido=contenido))
    fila.data_json = json.dumps(row, ensure_ascii=False)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        os.remove(ruta)
        raise
    return jsonify({'url': row['ADJUNTO CORREO VALIDACION'], 'nombre': row['NOMBRE CORREO VALIDACION']})


@bp.route('/api/rendicion/correo/<int:origen_id>/<nombre>')
@login_required
def descargar_correo_validacion(origen_id, nombre):
    if not _puede_gestionar():
        return jsonify({'error': 'No tienes permisos.'}), 403
    proy = _proy()
    fila = NucleusData.query.filter_by(id=origen_id, proyecto_id=proy.id).first() if proy else None
    if not fila or secure_filename(nombre) != nombre:
        return jsonify({'error': 'Correo no encontrado.'}), 404
    row = json.loads(fila.data_json or '{}')
    if row.get('ADJUNTO CORREO VALIDACION') != '/api/rendicion/correo/%s/%s' % (origen_id, nombre):
        return jsonify({'error': 'Correo no encontrado.'}), 404
    adjunto = RendicionCorreo.query.filter_by(origen_id=origen_id, nombre=nombre).first()
    if adjunto:
        return send_file(io.BytesIO(adjunto.contenido), as_attachment=True,
                         download_name=adjunto.nombre_original, mimetype='application/vnd.ms-outlook')
    if evidencia_usa_b2():
        try:
            objeto = b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'],
                                            Key=f'rendicion_correos/{origen_id}/{nombre}')
            return send_file(io.BytesIO(objeto['Body'].read()), as_attachment=True,
                             download_name=row.get('NOMBRE CORREO VALIDACION') or nombre)
        except Exception:
            if not os.path.isfile(os.path.join(_correo_folder(origen_id), nombre)):
                return jsonify({'error': 'No se pudo recuperar el correo del almacenamiento. Reintenta en unos momentos.'}), 503
    return send_from_directory(_correo_folder(origen_id), nombre, as_attachment=True, download_name=row.get('NOMBRE CORREO VALIDACION') or nombre)


@bp.route('/api/rendicion/por_wo')
@login_required
def rendiciones_por_wo():
    key = str(request.args.get('key') or '').strip()
    pid = request.args.get('proyecto_id', type=int)
    proyectos = get_menu_proyectos(session.get('user_id'), session.get('rol'))
    if not pid or not any(p.id == pid and p.nombre in ('FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT') for p in proyectos):
        return jsonify({'error': 'No tienes acceso a este WO.'}), 403
    if not key or not NucleusData.query.filter_by(proyecto_id=pid, key_value=key).first():
        return jsonify({'error': 'WO no encontrado.'}), 404
    proyecto = _proy()
    if not proyecto:
        return jsonify({'lista': []})
    def normalizar(texto):
        return re.sub(r'[^a-z0-9]', '', ''.join(c for c in unicodedata.normalize('NFKD', str(texto or '')).lower() if not unicodedata.combining(c)))
    campos_wo = {'numerocmpmplm', 'numerocm', 'numerowo', 'numerodewo', 'numerocmpm', 'numeropmplm'}
    from services.recursos_flm import familia
    from sqlalchemy import func
    origen_nombre = next(p.nombre for p in proyectos if p.id == pid)
    fuentes_wo = [p.id for p in Proyecto.query.filter(Proyecto.nombre.in_(('FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO','FLM - PEXT')))]
    ambiguo = NucleusData.query.filter(NucleusData.proyecto_id.in_(fuentes_wo), func.lower(NucleusData.key_value)==key.lower()).count() > 1
    lista = []
    for fila in NucleusData.query.filter_by(proyecto_id=proyecto.id).order_by(NucleusData.id.desc()).all():
        try:
            datos = json.loads(fila.data_json or '{}')
        except (ValueError, TypeError):
            continue
        campos = {normalizar(c): v for c, v in datos.items()}
        negocio = familia(campos.get('nombredelproyecto') or campos.get('proyecto') or campos.get('cliente'))
        if negocio and negocio != familia(origen_nombre):continue
        if not negocio and ambiguo:continue
        valores = [v for c,v in campos.items() if c in campos_wo]
        codigos = [str(c).strip().casefold() for v in valores for c in (v if isinstance(v,list) else re.split(r'[,;|\n]+',str(v or '')))]
        if key.casefold() not in codigos:
            continue
        lista.append({'id': fila.id, 'codigo': datos.get('CODIGO DEPOSITO') or fila.key_value,
            'estado': _estado_de(datos), 'tecnico': campos.get('tecnicobeneficiario') or '',
            'motivo': _motivo_de(datos), 'monto': _monto_de(datos),
            'fecha': campos.get('marcatemporal') or datos.get('FECHA VALIDACION') or ''})
    return jsonify({'lista': lista})

@bp.route('/api/rendicion/validadores', methods=['GET', 'POST'])
@login_required
def configurar_validadores():
    return jsonify(error='Esta configuración ya no se utiliza. El acceso depende de los proyectos asignados.'), 410

@bp.route('/api/rendicion/solicitud', methods=['PATCH'])
@login_required
def corregir_solicitud():
    from models import HistorialCambios
    from services.rendicion_correcciones import validar_cambios, normalizar
    from services.rendicion_personal import completar_personal, indice_personal, documento, presentar_beneficiario_dataper
    if not _puede_gestionar() or session.get('rol') not in ROLES_ACCION:
        return jsonify(error='No tienes permiso para corregir solicitudes.'),403
    payload=request.get_json(silent=True) or {}
    if not isinstance(payload,dict):
        return jsonify(error='Solicitud inválida.'),400
    proy=_proy()
    fila=NucleusData.query.filter_by(proyecto_id=proy.id,key_value=str(payload.get('key') or '')).with_for_update().first() if proy else None
    if not fila:
        return jsonify(error='Solicitud no encontrada.'),404
    row=json.loads(fila.data_json or '{}')
    if _etapa_de(row)!='VALIDACION':
        return jsonify(error='Solo puedes corregir la solicitud mientras esté en Validación.'),409
    if payload.get('revision',0)!=row.get('_CORRECCION_REV',0):
        return jsonify(error='Otro usuario corrigió esta solicitud. Recarga antes de continuar.'),409
    try:
        cambios=validar_cambios(payload.get('cambios'),row)
    except ValueError as error:
        return jsonify(error=str(error)),400
    nuevos={**row,**cambios}
    campos_doc=[k for k in cambios if normalizar(k)=='documentodelbeneficiario']
    if campos_doc:
        nuevos.pop('_PERSONAL_CORRECCION_MANUAL',None)
        completar_personal(nuevos,indice_personal())
        nuevos.update(cambios)
    identidad=any(normalizar(k) in ('tecnicobeneficiario','departamento') for k in cambios)
    if identidad:
        nuevos.setdefault('_PERSONAL_ORIGINAL',{'tecnico':row.get('Técnico beneficiario',''),'documento':row.get('Documento del beneficiario',''),'departamento':row.get('DEPARTAMENTO','')})
        nuevos['_PERSONAL_CORRECCION_MANUAL']=True
    auditoria=[]
    for campo,valor in nuevos.items():
        if campo.startswith('_') or valor==row.get(campo):
            continue
        if campo in cambios or campo in ('Técnico beneficiario','DEPARTAMENTO'):
            auditoria.append(HistorialCambios(proyecto_id=proy.id,usuario_id=session.get('user_id'),
                username=audit_user() or '',key_value=fila.key_value,campo_modificado=campo,
                valor_anterior=str(row.get(campo) or ''),valor_nuevo=str(valor or '')))
    if not auditoria:
        return jsonify(success=True,newData=presentar_beneficiario_dataper({**row,'_key':fila.key_value},indice_personal(),solo_meta=True))
    nuevos['_CORRECCION_REV']=row.get('_CORRECCION_REV',0)+1
    nuevos['_CORREGIDO_POR']=audit_user() or ''
    nuevos['_FECHA_CORRECCION']=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db.session.add_all(auditoria)
    fila.data_json=json.dumps(nuevos,ensure_ascii=False)
    db.session.commit()
    return jsonify(success=True,newData=presentar_beneficiario_dataper({**nuevos,'_key':fila.key_value},indice_personal(),solo_meta=True))


RENDICION_CSV_TEMPLATE = 'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
# Claves AppConfig usadas por el módulo Rendición:
#   rendicion_csv_url  -> URL CSV pública del Google Form
#   rendicion_sync_key -> token de sincronización (cron externo)


@bp.route('/api/rendicion/sync', methods=['GET', 'POST'])
def api_rendicion_sync():
    """Importa SOLO las filas nuevas del Google Form al módulo 'Rendicion'.

    Autorización por dos vías:
      - Botón "Sincronizar" en la web: cualquier usuario que tenga el módulo
        Rendicion habilitado (no depende del rol).
      - Cron externo: ?key=<rendicion_sync_key> (sin sesión).
    No toca filas existentes: solo inserta claves nuevas (Marca temporal).
    """
    key = request.args.get('key') or (request.get_json(silent=True) or {}).get('key', '')
    cfg = AppConfig.query.filter_by(clave='rendicion_sync_key').first()
    key_valida = bool(cfg and cfg.valor and key == cfg.valor)
    if not key_valida:
        autorizado_web = bool(
            session.get('user_id')
            and puede_rendicion(session.get('user_id'), session.get('rol'),
                                None)
        )
        if not autorizado_web:
            if not key:
                return jsonify({'error': 'Falta la key de sincronización.'}), 400
            return jsonify({'error': 'Key de sincronización inválida.'}), 403

    from services.alcance_proyectos import importacion_rendicion
    with importacion_rendicion():
        return _importar_solicitudes()


def _importar_solicitudes():
    proy = Proyecto.query.filter_by(nombre='Rendicion').first()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404

    url_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='rendicion_csv_url').first()
    csv_url = (url_cfg.valor if url_cfg and url_cfg.valor else '').strip()
    if not csv_url:
        return jsonify({'error': 'No hay URL de CSV configurada (rendicion_csv_url).'}), 500

    # Descargar CSV
    try:
        req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as e:
        return jsonify({'error': 'No se pudo descargar el CSV: %s' % e}), 502
    text = raw.decode('utf-8-sig', errors='replace')

    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    # Clave del módulo: la que esté configurada en primary_key (Marca temporal en Rendicion).
    pk_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='primary_key').first()
    pk_col = (pk_cfg.valor if pk_cfg and pk_cfg.valor else '').strip() or 'Marca temporal'
    if pk_col not in fields:
        return jsonify({'error': 'El CSV no tiene la columna clave "%s".' % pk_col}), 502

    # 'Observaciones' del form se renombra para no chocar con la columna manual OBSERVACIONES.
    renombrar = {'Observaciones': 'Observaciones (Form)'}

    # Claves que escribe el sistema/flujo del módulo: si el form trajera un
    # encabezado idéntico, se desplaza con sufijo ' (Form)' para no pisarlas.
    claves_sistema = {
        '_TIPO_GASTO_HOMOLOGACION',
        '_PERSONAL_CORRECCION_MANUAL', '_CORRECCION_REV', '_CORREGIDO_POR', '_FECHA_CORRECCION',
        'DEPARTAMENTO', 'VERIFICACIÓN PERSONAL', '_PERSONAL_ORIGINAL', '_PERSONAL_CRUCE',
        'Técnico beneficiario (Form)', 'Documento del beneficiario (Form)', 'Cruce de personal',
        'PRESUPUESTO', 'N° COTIZACION', '_COTIZACION_VINCULO', '_CONTROL_COTIZACION',
        'ESTADO', 'SUBESTADO', 'MOTIVO RECHAZO', 'INTERACCION', 'CODIGO DEPOSITO', 'OBSERVACIONES',
        'FECHA PAGO', 'MONTO PAGO', 'FOTO PAGO', 'FOTOS SUSTENTO',
        'COMENTARIOS SUSTENTO', 'FECHA SUSTENTO', 'FECHA RECHAZO',
        'RECHAZADO POR', 'FECHA VALIDACION', 'VALIDADO POR',
        'DEPOSITADO POR', 'SUSTENTADO POR', 'EDITADO POR',
        'RECHAZADO DESDE', 'VECES RECHAZADO', 'DEVUELTO POR',
        'FECHA DEVOLUCION', '_SUSTENTO_MARCAS',
        'OBSERVADO POR', 'FECHA OBSERVACION', 'ARCHIVADO POR', 'FECHA ARCHIVO',
        'DESARCHIVADO POR', 'FECHA DESARCHIVO', '_HISTORIAL_FLUJO',
        '_RECHAZO_ETAPA', 'ANULADO DESDE', 'ANULADO POR', 'FECHA ANULACION',
    }

    # Esquema DINÁMICO: las columnas del grid del form son exactamente las que
    # traiga el CSV HOY. Agregar, quitar o renombrar una pregunta en el form se
    # refleja en el próximo sync (sin tocar código): las nuevas aparecen, las
    # dadas de baja (o renombradas) dejan de mostrarse.
    # El 2.º formulario (SUSTENTO_*) y las claves que escribe el flujo NO vienen
    # del CSV: este sync las conserva en lugar de borrarlas.
    schema_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='app_schema').first()
    try:
        schema_previo = set(json.loads(schema_cfg.valor)) if schema_cfg and schema_cfg.valor else set()
    except Exception:
        schema_previo = set()
    sistema_cols = {c for c in schema_previo
                    if c.startswith('SUSTENTO_') or c in claves_sistema}
    form_previas = schema_previo - sistema_cols

    mapa_cols = {}
    for f in fields:
        if f is None or not str(f).strip():
            continue
        nombre_col = renombrar.get(str(f).strip(), str(f).strip())
        if nombre_col in claves_sistema:
            nombre_col = '%s (Form)' % nombre_col
        if nombre_col not in mapa_cols.values():
            mapa_cols[f] = nombre_col
    form_actual = set(mapa_cols.values())
    columnas_agregadas = sorted(form_actual - form_previas)
    columnas_quitadas = sorted(form_previas - form_actual)
    schema_cols = form_actual | sistema_cols

    from services.rendicion_personal import indice_personal, completar_personal
    personal = indice_personal()
    verificadas = 0
    pendientes_personal = 0
    nuevas = 0
    omitidas = 0
    t0 = time.time()
    # Claves existentes en una sola consulta (antes: 1 query por fila del CSV).
    existentes = {r[0] for r in NucleusData.query.with_entities(NucleusData.key_value)
                  .filter_by(proyecto_id=proy.id).all()}
    for row in reader:
        from services.rendicion_origen import recibir_en_nucleus
        if not recibir_en_nucleus(row):
            omitidas += 1
            continue
        datos = {}
        for f in fields:
            nombre_col = mapa_cols.get(f)
            if not nombre_col:
                continue
            datos[nombre_col] = (row.get(f) or '').strip()
        
        id_sol = str(datos.get(pk_col, '') or '').strip()
        if not id_sol:
            omitidas += 1
            continue
        if id_sol in existentes:
            omitidas += 1
            continue
        from services.rendicion_gastos import clasificar as homologar_gasto
        datos = homologar_gasto(datos)
        completar_personal(datos, personal)
        if datos['VERIFICACIÓN PERSONAL'] == 'Verificado':
            verificadas += 1
        else:
            pendientes_personal += 1
        db.session.add(NucleusData(proyecto_id=proy.id, key_value=id_sol,
                                   data_json=safe_json_dumps(datos)))
        existentes.add(id_sol)
        schema_cols.update(set(datos.keys()))
        nuevas += 1

    # Completar los registros anteriores sin modificar importes, etapas ni evidencias.
    personal_actualizado = 0
    for registro in NucleusData.query.filter_by(proyecto_id=proy.id).yield_per(500):
        anteriores = json.loads(registro.data_json or '{}')
        cruzados = completar_personal(dict(anteriores), personal)
        if cruzados['_PERSONAL_CRUCE']['estado'] not in ('VERIFICADO', 'SIN DEPARTAMENTO EN PERSONAL'):
            continue
        if cruzados != anteriores:
            registro.data_json = safe_json_dumps(cruzados)
            personal_actualizado += 1
    schema_cols.add('DEPARTAMENTO')
    schema_cols.update({'Técnico beneficiario (Form)', 'Documento del beneficiario (Form)', 'Cruce de personal'})

    # Persistir esquema DINÁMICO (reemplaza columnas dadas de baja, no solo agrega)
    if schema_cfg:
        schema_cfg.valor = safe_json_dumps(sorted(schema_cols))
    else:
        db.session.add(AppConfig(proyecto_id=proy.id, clave='app_schema',
                                 valor=safe_json_dumps(sorted(schema_cols))))
    # La sincronización actualiza el esquema, pero conserva las vistas del administrador.
    db.session.commit()

    return jsonify({
        'success': True,
        'nuevas': nuevas,
        'personal_verificado': verificadas,
        'personal_actualizado': personal_actualizado,
        'personal_pendiente_verificar': pendientes_personal,
        'omitidas_existentes': omitidas,
        'columnas_agregadas': columnas_agregadas,
        'columnas_quitadas': columnas_quitadas,
        'segundos': round(time.time() - t0, 2),
    })
@bp.route('/api/rendicion/sync_sustentos', methods=['POST'])
def api_rendicion_sync_sustentos():
    """Sincroniza los sustentos desde la segunda hoja de Google Sheets."""
    autorizado = bool(session.get('user_id')
                       and puede_rendicion(session.get('user_id'), session.get('rol'),
                                           None))
    if not autorizado:
        return jsonify({'error': 'No autorizado.'}), 403

    from services.alcance_proyectos import importacion_rendicion
    with importacion_rendicion():
        return _importar_sustentos()


def _importar_sustentos():
    proy = Proyecto.query.filter_by(nombre='Rendicion').first()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404

    # URL configurable (AppConfig rendicion_sustentos_url) con fallback a la hoja fija.
    url_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='rendicion_sustentos_url').first()
    csv_url = ((url_cfg.valor if url_cfg and url_cfg.valor else '').strip()
               or 'https://docs.google.com/spreadsheets/d/18CYUhXGN8jWk4hzr194p3vhdU6H90WD-O0Aw77WxgEY/export?format=csv&gid=831408062')
    try:
        req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as e:
        return jsonify({'error': 'No se pudo descargar el CSV de Sustentos: %s' % e}), 502
    
    text = raw.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []

    # Buscamos la columna CODIGO DEPOSITO
    col_codigo = next((f for f in fields if 'codigo' in str(f).lower() and 'deposito' in str(f).lower()), None)
    if not col_codigo:
        # Fallback a la primera columna o un nombre estandar
        col_codigo = 'CODIGO DEPOSITO' if 'CODIGO DEPOSITO' in fields else (fields[0] if fields else None)
    
    if not col_codigo:
         return jsonify({'error': 'No se encontro la columna CODIGO DEPOSITO en la hoja.'}), 400

    # Independencia del form 2: cada envío (Marca temporal) aplica UNA sola vez.
    # Si la hoja no trae columna de fecha/hora, se conserva el comportamiento
    # anterior (refresh de SUSTENTO_*) por compatibilidad.
    col_marca = next((f for f in fields
                      if 'marca' in str(f).lower() and 'temporal' in str(f).lower()), None)
    if not col_marca:
        col_marca = next((f for f in fields
                          if str(f).strip().lower() in ('marca temporal', 'timestamp',
                                                        'marca de tiempo')), None)

    # Los datos del 2.º formulario se guardan en la fila como SUSTENTO_* y SÍ
    # son columnas del grid: se agregan al esquema al final del sync. Quedan
    # ocultas por defecto (no estorban en Validación/Depósitos) y las pestañas
    # Evidencia y Rendición las muestran con showPrefijos.
    schema_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='app_schema').first()

    actualizados = 0
    omitidos = 0
    no_encontrados = 0
    nuevas_sustento = set()
    t0 = time.time()

    # Índice único por CODIGO DEPOSITO (antes: full-scan por cada fila del CSV).
    idx_cod = {}
    for d in NucleusData.query.filter_by(proyecto_id=proy.id).all():
        try:
            dj = json.loads(d.data_json)
        except Exception:
            continue
        cod = str(dj.get('CODIGO DEPOSITO', '') or '').strip()
        if cod and cod not in idx_cod:
            idx_cod[cod] = (d, dj)

    for row in reader:
        cod = (row.get(col_codigo) or '').strip()
        if not cod: continue

        target, target_dict = idx_cod.get(cod, (None, None))
        if not target:
            no_encontrados += 1
            continue
            
        estado_actual = str(target_dict.get('ESTADO', '')).strip().upper()
        from blueprints.rendicion import _etapa_de
        rechazo_evidencia = estado_actual == 'RECHAZADO' and _etapa_de(target_dict) == 'EVIDENCIA'
        if estado_actual not in ('DEPOSITADO', 'CON SUSTENTO', 'OBSERVADO') and _etapa_de(target_dict) != 'OBSERVADO' and not rechazo_evidencia:
            omitidos += 1
            continue

        # Cada envío del 2.º formulario aplica una sola vez (append-only por
        # Marca temporal): los cambios posteriores en el form ya no re-escriben
        # lo que se haya corregido en la app (independencia del form 2).
        marca_actual = None
        if col_marca:
            marca_actual = str(row.get(col_marca) or '').strip()
            if not marca_actual:
                omitidos += 1
                continue
            procesadas = set()
            for x in str(target_dict.get('_SUSTENTO_MARCAS', '') or '').replace(';', '\n').split('\n'):
                x = x.strip()
                if x:
                    procesadas.add(x)
            if marca_actual in procesadas:
                omitidos += 1
                continue

        for k, v in row.items():
            if k and k != col_codigo and k != col_marca:
                col = 'SUSTENTO_%s' % k.upper()
                target_dict[col] = str(v).strip()
                nuevas_sustento.add(col)

        if estado_actual == 'DEPOSITADO' or rechazo_evidencia:
            target_dict['ESTADO'] = 'CON SUSTENTO'
            target_dict['SUBESTADO'] = ''
        if marca_actual:
            procesadas.add(marca_actual)
            target_dict['_SUSTENTO_MARCAS'] = ';'.join(sorted(procesadas))
        target.data_json = safe_json_dumps(target_dict)
        actualizados += 1

    # ── Columnas del 2.º formulario: se suman al esquema del módulo ─────────
    try:
        schema_previo = list(json.loads(schema_cfg.valor)) if schema_cfg and schema_cfg.valor else []
    except Exception:
        schema_previo = []
    faltantes = sorted(set(nuevas_sustento) - set(schema_previo))
    if faltantes and schema_cfg:
        schema_cfg.valor = safe_json_dumps(sorted(set(schema_previo) | set(nuevas_sustento)))

    db.session.commit()

    return jsonify({
        'success': True,
        'actualizados': actualizados,
        'omitidos_por_estado': omitidos,
        'no_encontrados': no_encontrados,
        'columnas_sustento': len(nuevas_sustento),
        'columnas_nuevas': faltantes,
        'segundos': round(time.time() - t0, 2)
    })
