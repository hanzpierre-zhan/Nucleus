# -*- coding: utf-8 -*-
import os, io, re, json, time, glob, zipfile, gzip, mimetypes, tempfile
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timedelta
from collections import Counter
from flask import (Blueprint, request, jsonify, session, redirect, url_for,
                   render_template, current_app, make_response,
                   send_from_directory, send_file, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
import pandas as pd
from PIL import Image, ImageOps
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
from db import db
from models import (Usuario, Proyecto, AppConfig, TokenStore, NucleusData,
                    NucleusHistory, FiltroMaestro, TablaMaestra,
                    ReglaEstadoManual, AccesoProyecto, KpiConfig,
                    HistorialCambios, Tecnico, Cotizacion)
from services import *


bp = Blueprint('cotizacion', __name__)


def _puede_cotizaciones():
    """True si el usuario puede usar el módulo Cotizaciones (ver services)."""
    return puede_cotizaciones(
        session.get('user_id'),
        str(session.get('rol') or '').strip().lower(),
        session.get('current_proyecto_nombre'),
    )



@bp.route('/api/cotizacion/estado', methods=['GET'])
@login_required
def api_cotizacion_estado():
    """Devuelve si la cotización de este ticket ya fue generada (bloqueada)."""
    pid = session.get('current_proyecto_id')
    key = request.args.get('key', '').strip()
    if not pid or not key:
        return jsonify({'bloqueada': False})
    cot = Cotizacion.query.filter_by(proyecto_id=pid, key_value=key).first()
    if cot:
        return jsonify({
            'bloqueada': cot.bloqueada,
            'numero': cot.numero,
            'nota': cot.nota,
            'cotizado_por': cot.cotizado_por,
            'revisado_por': cot.revisado_por,
            'fecha': (cot.fecha_generacion - timedelta(hours=5)).strftime('%d/%m/%Y') if cot.fecha_generacion else ''
        })
    return jsonify({'bloqueada': False})


@bp.route('/api/cotizacion/lista', methods=['GET'])
@login_required
def api_cotizacion_lista():
    """Devuelve todas las cotizaciones del ticket (puede haber varias)."""
    pid = session.get('current_proyecto_id')
    key = request.args.get('key', '').strip()
    if not pid or not key:
        return jsonify({'lista': []})
    # FLM <-> FLM - ENTEL: las cotizaciones del CM se muestran desde ambos proyectos,
    # sin importar en cuál fueron creadas.
    pids = [pid]
    her = _flm_hermano_id(pid)
    if her is not None:
        pids.append(her)
    cots = Cotizacion.query.filter(
        Cotizacion.proyecto_id.in_(pids), Cotizacion.key_value == key
    ).order_by(Cotizacion.id.asc()).all()
    lista = [{
        'id': c.id,
        'numero': c.numero,
        'nota': c.nota,
        'cotizado_por': c.cotizado_por,
        'revisado_por': c.revisado_por,
        'fecha': (c.fecha_generacion - timedelta(hours=5)).strftime('%d/%m/%Y') if c.fecha_generacion else '',
        'bloqueada': c.bloqueada,
        'gastos': json.loads(c.gastos_json or '[]'),
        'mano_obra': json.loads(c.mano_obra_json or '[]'),
        'formato': c.formato or '',
        'site': c.site or '',
        'supervisor': c.supervisor or '',
        'objetivo': c.nota or '',
        'items': json.loads(c.items_json or '[]'),
    } for c in cots]
    return jsonify({'lista': lista})


@bp.route('/api/cotizacion/registro', methods=['GET'])
@login_required
def api_cotizacion_registro():
    """Cotizaciones registradas en el módulo 'Cotizaciones' asociadas a un WO
    de FLM (match por NUMERO WO). Se muestran en la pestaña Cotización del WO."""
    key = request.args.get('key', '').strip()
    if not key:
        return jsonify({'lista': []})
    cot_proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not cot_proy:
        return jsonify({'lista': []})
    klow = key.lower()
    lista = []
    regs = NucleusData.query.filter_by(proyecto_id=cot_proy.id).order_by(NucleusData.id.asc()).all()
    for r in regs:
        try:
            d = json.loads(r.data_json)
        except Exception:
            continue
        wo = str(d.get('NUMERO WO', '') or '').strip()
        if not wo or wo.lower() != klow:
            continue
        try:
            items = json.loads(d.get('ITEMS_JSON') or '[]')
        except Exception:
            items = []
        lista.append({
            'id': 'R' + str(r.id),
            'numero': str(d.get('N° COTIZACION', '') or ''),
            'fecha': str(d.get('FECHA', '') or ''),
            'formato': 'cobra',
            'site': str(d.get('SITE', '') or ''),
            'supervisor': str(d.get('SUPERVISOR', '') or ''),
            'objetivo': str(d.get('OBJETIVO', '') or ''),
            'ticket': str(d.get('TICKET', '') or ''),
            'gestor': str(d.get('GESTOR', '') or ''),
            'generada': str(d.get('GENERADA', '') or ''),
            'sub_total': str(d.get('SUB TOTAL + FEE', '') or ''),
            'items': items,
        })
    return jsonify({'lista': lista})


@bp.route('/api/cotizacion/descargar_registro', methods=['POST'])
@login_required
def api_cotizacion_descargar_registro():
    """Descarga el PDF de una cotización registrada en el módulo 'Cotizaciones'."""
    data = request.json or {}
    rid_raw = str(data.get('registro_id', '')).lstrip('R')
    try:
        rid = int(rid_raw)
    except (ValueError, TypeError):
        return jsonify({'error': 'Registro inválido'}), 400
    cot_proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not cot_proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe'}), 404
    rec = NucleusData.query.filter_by(id=rid, proyecto_id=cot_proy.id).first()
    if not rec:
        return jsonify({'error': 'Cotización no encontrada'}), 404
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    try:
        items = json.loads(d.get('ITEMS_JSON') or '[]')
    except Exception:
        items = []
    numero = str(d.get('N° COTIZACION', '') or '')
    try:
        pdf_bytes = _generar_pdf_cotizacion_cobra(
            numero=numero,
            site=str(d.get('SITE', '') or ''),
            supervisor=str(d.get('SUPERVISOR', '') or ''),
            objetivo=str(d.get('OBJETIVO', '') or ''),
            ticket=str(d.get('TICKET', '') or ''),
            elaborado_por=str(d.get('GESTOR', '') or ''),
            items=items,
            # FECHA registrada de la cotización (no la fecha de descarga)
            fecha=d.get('FECHA')
        )
    except Exception as e:
        return jsonify({'error': f'Error al generar PDF: {str(e)}'}), 500
    from flask import make_response
    resp = make_response(pdf_bytes)
    safe_num = numero.replace('/', '-').replace(' ', '_') or 'cotizacion'
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Cotizacion_{safe_num}.pdf'
    return resp


@bp.route('/api/cotizacion/descargar_lote', methods=['POST'])
@login_required
def api_cotizacion_descargar_lote():
    """Descarga un ZIP con los PDFs de las cotizaciones GENERADAS cuyo campo
    FECHA cae dentro del rango [desde, hasta] (fechas 'YYYY-MM-DD').
    Límite: rango máximo 366 días y 200 cotizaciones por lote."""
    if not _puede_cotizaciones():
        return jsonify({'error': 'No tienes el módulo Cotizaciones en tu perfil.'}), 403
    data = request.json or {}
    desde_s = str(data.get('desde', '') or '').strip()
    hasta_s = str(data.get('hasta', '') or '').strip()
    try:
        desde_d = datetime.strptime(desde_s, '%Y-%m-%d').date()
        hasta_d = datetime.strptime(hasta_s, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Rango de fechas inválido.'}), 400
    if desde_d > hasta_d:
        return jsonify({'error': 'La fecha "desde" no puede ser mayor que "hasta".'}), 400
    if (hasta_d - desde_d).days > 366:
        return jsonify({'error': 'El rango máximo es 366 días. Acorte las fechas.'}), 400
    cot_proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not cot_proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe'}), 404
    seleccion = []
    for rec in NucleusData.query.filter_by(proyecto_id=cot_proy.id).order_by(NucleusData.id.asc()).all():
        try:
            d = json.loads(rec.data_json)
        except Exception:
            continue
        if str(d.get('GENERADA', '') or '') != '1':
            continue
        fdt = _parse_fecha_registro(d.get('FECHA'))
        if fdt is None:
            continue
        if not (desde_d <= fdt.date() <= hasta_d):
            continue
        seleccion.append((rec, d))
    if not seleccion:
        return jsonify({'error': 'No hay cotizaciones generadas en ese rango de fechas.'}), 404
    MAX_LOTE = 200
    if len(seleccion) > MAX_LOTE:
        return jsonify({'error': f'Son {len(seleccion)} cotizaciones; el máximo por lote es {MAX_LOTE}. Acorte el rango.'}), 400
    zbuf = io.BytesIO()
    usados = set()
    try:
        with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rec, d in seleccion:
                try:
                    items = json.loads(d.get('ITEMS_JSON') or '[]')
                except Exception:
                    items = []
                numero = str(d.get('N° COTIZACION', '') or rec.key_value or '').strip() or ('registro_%d' % rec.id)
                numero_wo = str(d.get('NUMERO WO', '') or '').strip()
                pdf_bytes = _generar_pdf_cotizacion_cobra(
                    numero=numero,
                    site=str(d.get('SITE', '') or d.get('NOMBRE SITE', '') or ''),
                    supervisor=str(d.get('SUPERVISOR', '') or ''),
                    objetivo=str(d.get('OBJETIVO', '') or ''),
                    ticket=numero_wo if numero_wo else 'CM-PENDIENTE',
                    elaborado_por=str(d.get('GESTOR', '') or session.get('username', '')),
                    items=items,
                    # FECHA registrada de cada cotización (no la fecha de descarga)
                    fecha=d.get('FECHA')
                )
                safe = re.sub(r'[^\w\-.]+', '_', numero).strip('_') or ('registro_%d' % rec.id)
                nombre = f'Cotizacion_{safe}.pdf'
                k = 2
                while nombre in usados:
                    nombre = f'Cotizacion_{safe}_{k}.pdf'
                    k += 1
                usados.add(nombre)
                zf.writestr(nombre, pdf_bytes)
    except Exception as e:
        return jsonify({'error': f'Error al generar el lote: {str(e)}'}), 500
    from flask import make_response
    resp = make_response(zbuf.getvalue())
    resp.headers['Content-Type'] = 'application/zip'
    resp.headers['Content-Disposition'] = (
        f"attachment; filename=Cotizaciones_{desde_s.replace('-', '')}_{hasta_s.replace('-', '')}.zip")
    return resp


@bp.route('/api/cotizacion/next_seq', methods=['GET', 'POST'])
@login_required
def api_cotizacion_next_seq():
    cot_proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not cot_proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe'}), 404
    if request.method == 'GET':
        cfg = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='cotizacion_next_seq').first()
        try:
            val = int(cfg.valor) if cfg and cfg.valor else 30
        except Exception:
            val = 30
        return jsonify({'next': val})
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo el admin puede configurar el correlativo'}), 403
    data = request.json or {}
    try:
        nxt = int(data.get('next', 0))
        if nxt < 1 or nxt > 9999999:
            raise ValueError
    except Exception:
        return jsonify({'error': 'Valor inválido (1-9999999)'}), 400
    cfg = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='cotizacion_next_seq').first()
    if not cfg:
        cfg = AppConfig(proyecto_id=cot_proy.id, clave='cotizacion_next_seq', valor=str(nxt))
        db.session.add(cfg)
    else:
        cfg.valor = str(nxt)
    db.session.commit()
    return jsonify({'success': True, 'next': nxt})


@bp.route('/api/cotizacion/previsualizar', methods=['POST'])
@login_required
def api_cotizacion_previsualizar():
    """Genera PDF de previsualización sin guardar ni consumir correlativo."""
    data = request.json or {}
    numero = str(data.get('numero', '') or '').strip()
    site = str(data.get('site', '') or data.get('nombre site', '') or '').strip()
    supervisor = str(data.get('supervisor', '') or '').strip()
    objetivo = str(data.get('objetivo', '') or str(data.get('nota', '') or '')).strip()
    ticket = str(data.get('ticket', '') or str(data.get('numero_wo', '') or '')).strip()
    if not ticket:
        ticket = 'CM-PENDIENTE'
    items = data.get('items', [])
    # Fecha del formulario (FECHA Y HORA); si no viene, el PDF usa la actual
    fecha_form = data.get('fecha') or ''
    # Validación mínima igual que generar
    if not numero:
        return jsonify({'error': 'Falta N° Cotización'}), 400
    try:
        pdf_bytes = _generar_pdf_cotizacion_cobra(
            numero=numero,
            site=site,
            supervisor=supervisor,
            objetivo=objetivo,
            ticket=ticket,
            elaborado_por=str(session.get('username', '') or ''),
            items=items,
            fecha=fecha_form or None
        )
    except Exception as e:
        return jsonify({'error': f'Error al generar PDF: {str(e)}'}), 500
    from flask import make_response
    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'inline; filename=Preview_{numero.replace("/", "-")}.pdf'
    return resp


@bp.route('/api/cotizacion/registro_pdf', methods=['POST'])
@login_required
def api_cotizacion_registro_pdf():
    """Descarga directa del PDF desde la tabla del módulo Cotizaciones."""
    rec, _proy, err = _obtener_registro_cotizacion()
    if err:
        return err
    try:
        return _cotizacion_registro_pdf_response(rec)
    except Exception as e:
        return jsonify({'error': f'Error al generar PDF: {str(e)}'}), 500


@bp.route('/api/cotizacion/registro_generar', methods=['POST'])
@login_required
def api_cotizacion_registro_generar():
    """Marca la cotización como GENERADA (bloquea edición para gestores) y devuelve el PDF."""
    rec, _proy, err = _obtener_registro_cotizacion()
    if err:
        return err
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    d['GENERADA'] = '1'
    rec.data_json = json.dumps(d, ensure_ascii=False)
    db.session.commit()
    try:
        return _cotizacion_registro_pdf_response(rec)
    except Exception as e:
        return jsonify({'error': f'Error al generar PDF: {str(e)}'}), 500


@bp.route('/api/cotizacion/desbloquear', methods=['POST'])
@login_required
def api_cotizacion_desbloquear():
    """Solo admin puede desbloquear una cotización para permitir edición."""
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo admin puede desbloquear cotizaciones.'}), 403
    pid = session.get('current_proyecto_id')
    data = request.json or {}
    key = data.get('key', '').strip()
    cid = data.get('cotizacion_id')
    if not pid or not key:
        return jsonify({'error': 'Datos incompletos'}), 400
    query = Cotizacion.query.filter_by(proyecto_id=pid, key_value=key)
    if cid:
        query = query.filter_by(id=cid)
    cot = query.first()
    if not cot:
        return jsonify({'error': 'Cotización no encontrada'}), 404
    cot.bloqueada = False
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/api/cotizacion/eliminar', methods=['POST'])
@login_required
def api_cotizacion_eliminar():
    """Solo admin puede eliminar una cotización."""
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo admin puede eliminar cotizaciones.'}), 403
    pid = session.get('current_proyecto_id')
    data = request.json or {}
    key = data.get('key', '').strip()
    cid = data.get('cotizacion_id')
    if not pid or not key or not cid:
        return jsonify({'error': 'Datos incompletos'}), 400
    cot = Cotizacion.query.filter_by(proyecto_id=pid, key_value=key, id=cid).first()
    if not cot:
        return jsonify({'error': 'Cotización no encontrada'}), 404
    db.session.delete(cot)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/api/cotizacion/generar', methods=['POST'])
@login_required
def api_cotizacion_generar():
    """
    Guarda la cotización en BD (bloqueándola) y devuelve un PDF listo para descargar.
    Cada generación crea una NUEVA cotización para el ticket (puede haber varias).
    Datos del cliente fijos: HUAWEI DEL PERU, RUC 20507646728, etc.
    """
    pid = session.get('current_proyecto_id')
    user_rol = str(session.get('rol') or '').strip().lower()
    data = request.json or {}
    key = data.get('key', '').strip()
    if not pid or not key:
        return jsonify({'error': 'Datos incompletos'}), 400

    # Admin puede regenerar una cotización existente desbloqueada (opcional: cotizacion_id)
    cid = data.get('cotizacion_id')
    cot_existente = None
    if cid:
        cot_existente = Cotizacion.query.filter_by(proyecto_id=pid, key_value=key, id=cid).first()
        if cot_existente and cot_existente.bloqueada and user_rol not in ('zeno', 'suport'):
            # Liberación por estado: en Observado/Rechazado se puede regenerar
            # aunque la cotización siga marcada como bloqueada.
            _liberada = False
            _rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).first()
            if _rec:
                try:
                    _d_est = json.loads(_rec.data_json or '{}')
                except Exception:
                    _d_est = {}
                _liberada = str(_d_est.get('ESTADO COTIZACION', '') or '').strip() in ('Observado', 'Rechazado')
            if not _liberada:
                return jsonify({'error': 'La cotización ya fue generada y está bloqueada. Solo admin puede modificarla.'}), 403

    numero = data.get('numero', '').strip()
    nota = data.get('nota', '').strip()
    gastos = data.get('gastos', [])
    mano_obra = data.get('mano_obra', [])

    # Formato Cobra (FLM): items unicos con TIPO/UND/FEE
    formato = str(data.get('formato', '') or '').strip().lower()
    site = str(data.get('site', '') or data.get('nombre site', '') or data.get('NOMBRE SITE', '') or '').strip()
    supervisor = str(data.get('supervisor', '') or '').strip()
    objetivo = str(data.get('objetivo', '') or '').strip()
    items_cobra = data.get('items', [])
    if formato == 'cobra':
        nota = objetivo

    # Obtener nombre del gestor actual como "Cotizado por" y "Revisado por"
    usuario = db.session.get(Usuario, session.get('user_id'))
    nombre_gestor = (usuario.nombre or usuario.username) if usuario else (session.get('username') or '')

    # Guardar en BD (nueva fila si no se pasa cotizacion_id, o regenerar esa)
    if cot_existente:
        cot_existente.numero = numero
        cot_existente.nota = nota
        cot_existente.cotizado_por = nombre_gestor
        cot_existente.revisado_por = nombre_gestor
        cot_existente.gastos_json = json.dumps(gastos, ensure_ascii=False)
        cot_existente.mano_obra_json = json.dumps(mano_obra, ensure_ascii=False)
        cot_existente.fecha_generacion = datetime.utcnow()
        cot_existente.bloqueada = True
        if formato == 'cobra':
            cot_existente.formato = 'cobra'
            cot_existente.site = site
            cot_existente.supervisor = supervisor
            cot_existente.items_json = json.dumps(items_cobra, ensure_ascii=False)
        db.session.commit()
    else:
        cot_existente = Cotizacion(
            proyecto_id=pid,
            key_value=key,
            numero=numero,
            nota=nota,
            cotizado_por=nombre_gestor,
            revisado_por=nombre_gestor,
            gastos_json=json.dumps(gastos, ensure_ascii=False),
            mano_obra_json=json.dumps(mano_obra, ensure_ascii=False),
            fecha_generacion=datetime.utcnow(),
            bloqueada=True,
            formato='cobra' if formato == 'cobra' else '',
            site=site,
            supervisor=supervisor,
            items_json=json.dumps(items_cobra, ensure_ascii=False) if formato == 'cobra' else '[]'
        )
        db.session.add(cot_existente)
        db.session.commit()

    # Actualizar también los campos en NucleusData para que quede persistido
    rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).first()
    if rec:
        d = json.loads(rec.data_json)
        if formato == 'cobra':
            d['COTIZACION_ITEMS'] = json.dumps(items_cobra, ensure_ascii=False)
        else:
            d['COTIZACION_GASTOS'] = json.dumps(gastos, ensure_ascii=False)
            d['COTIZACION_MANO_OBRA'] = json.dumps(mano_obra, ensure_ascii=False)
        d['COTIZACION_NOTA'] = nota
        d['COTIZACION_NUMERO'] = numero
        d['COTIZACION_BLOQUEADA'] = '1'
        rec.data_json = json.dumps(d, ensure_ascii=False)
        db.session.commit()

    # Generar PDF
    try:
        if formato == 'cobra':
            pdf_bytes = _generar_pdf_cotizacion_cobra(
                numero=numero,
                site=site,
                supervisor=supervisor,
                objetivo=objetivo,
                ticket=key,
                elaborado_por=nombre_gestor,
                items=items_cobra
            )
        else:
            pdf_bytes = _generar_pdf_cotizacion(
                numero=numero,
                nota=nota,
                ticket=key,
                cotizado_por=nombre_gestor,
                revisado_por=nombre_gestor,
                fecha=ahora_peru().strftime('%d/%m/%Y'),
                gastos=gastos,
                mano_obra=mano_obra
            )
    except Exception as e:
        return jsonify({'error': f'Error al generar PDF: {str(e)}'}), 500

    from flask import make_response
    resp = make_response(pdf_bytes)
    safe_num = numero.replace('/', '-').replace(' ', '_')
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Cotizacion_{safe_num}.pdf'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Flujo de Peticiones (hojas Peticiones / Cotizaciones / Validación)
# ─────────────────────────────────────────────────────────────────────────────
# ESTADO es una columna interna: la gestiona el flujo, no se edita a mano.
#   - Pendiente            -> hoja Peticiones Y hoja Cotizaciones (duplicada)
#   - Pendiente Validacion -> hoja Validación
#   - Validado / Cerrado   -> fuera del flujo (ya no aparecen en las hojas)
# Cada petición genera un código interno COB-YYYY-MM-NNNNN (año-mes-consecutivo).
COTI_EST_PENDIENTE = 'Pendiente'
COTI_EST_VALIDACION = 'Pendiente Validacion'
COTI_EST_VALIDADO = 'Validado'
COTI_EST_CERRADO = 'Cerrado'
COTI_PROYECTOS = ('Claro Enterprise', 'Integratel')
COTI_TICKETS = ('CM', 'PM', 'PLM')
COTI_RESPONSABLES = ('LUCIANO', 'ROCIO', 'RICARDO')
COTI_TIPOS_PAGO = ('Refacturable', 'Fijo')
COTI_EXT_CORREO = ('.pdf', '.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif',
                   '.eml', '.msg', '.docx', '.doc', '.xlsx', '.xls')


def _proy_coti():
    return Proyecto.query.filter_by(nombre='Cotizaciones').first()


def _estado_peticion(d):
    return str(d.get('ESTADO', '') or '').strip() or COTI_EST_PENDIENTE


def _es_peticion(d):
    """Fila creada por el flujo de peticiones (tiene CODIGO INTERNO)."""
    return bool(str(d.get('CODIGO INTERNO') or '').strip())


def _codigo_interno_siguiente(proy_id, clave_seq):
    """Devuelve (consecutivo, codigo COB-YYYY-MM-NNNNN). El consecutivo es por mes."""
    cfg = AppConfig.query.filter_by(proyecto_id=proy_id, clave=clave_seq).first()
    try:
        prox = int(cfg.valor) if cfg and cfg.valor else 1
    except (ValueError, TypeError):
        prox = 1
    ano = clave_seq[-6:][:4]
    mes = clave_seq[-2:]
    return prox, 'COB-%s-%s-%05d' % (ano, mes, prox)


def _folder_coti(pid, key):
    return os.path.join(BASE_DIR, 'static', 'evidencia', str(pid),
                        secure_filename(str(key)))


@bp.route('/api/cotizacion/peticion/crear', methods=['POST'])
@login_required
def api_cotizacion_peticion_crear():
    """Registra una petición: genera el código interno COB-YYYY-MM-NNNNN y la
    deja en estado Pendiente (aparece en las hojas Peticiones y Cotizaciones)."""
    if not _puede_cotizaciones():
        return jsonify({'error': 'No tienes el módulo Cotizaciones en tu perfil.'}), 403
    proy = _proy_coti()
    if not proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe.'}), 404

    data = request.get_json(silent=True) or {}
    nombre_proyecto = str(data.get('nombre_proyecto') or '').strip()
    tipo_ticket = str(data.get('tipo_ticket') or '').strip().upper()
    responsable = str(data.get('responsable_presupuesto') or '').strip().upper()
    if not nombre_proyecto:
        return jsonify({'error': 'Ingresa el nombre de proyecto.'}), 400
    if tipo_ticket not in COTI_TICKETS:
        return jsonify({'error': 'Selecciona el tipo de ticket (CM/PM/PLM).'}), 400
    if responsable not in COTI_RESPONSABLES:
        return jsonify({'error': 'Selecciona el responsable del presupuesto.'}), 400

    usuario = db.session.get(Usuario, session.get('user_id'))
    nombre_gestor = (usuario.nombre or usuario.username) if usuario else (session.get('username') or '')

    fecha_sto = str(data.get('fecha_solicitud') or '').strip().replace('T', ' ')
    if not fecha_sto:
        fecha_sto = ahora_peru().strftime('%Y-%m-%d %H:%M:%S')

    now = ahora_peru()
    clave_seq = 'coti_peticion_seq_%04d%02d' % (now.year, now.month)
    prox, codigo = _codigo_interno_siguiente(proy.id, clave_seq)

    row = {
        'CODIGO INTERNO': codigo,
        'ESTADO': COTI_EST_PENDIENTE,
        'NOMBRE DE PROYECTO': nombre_proyecto,
        'NOMBRE DE GESTOR': nombre_gestor,
        'FECHA Y HORA DE SOLICITUD': fecha_sto,
        'TIPO DE TICKET': tipo_ticket,
        'RESPONSABLE DEL PRESUPUESTO': responsable,
        'SUPERVISOR RESPONSABLE': str(data.get('supervisor_responsable') or '').strip(),
        'TECNICO ASIGNADO': str(data.get('tecnico_asignado') or '').strip(),
        'TIPO DE PAGO': str(data.get('tipo_pago') or '').strip(),
        'LPU': str(data.get('lpu') or '').strip(),
        'NUMERO WO': str(data.get('numero_wo') or '').strip(),
        'INTERACCION': nombre_gestor,
    }

    cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave=clave_seq).first()
    if cfg:
        cfg.valor = str(prox + 1)
    else:
        db.session.add(AppConfig(proyecto_id=proy.id, clave=clave_seq, valor=str(prox + 1)))
    fila = NucleusData(proyecto_id=proy.id, key_value=codigo,
                       data_json=json.dumps(row, ensure_ascii=False))
    db.session.add(fila)
    db.session.commit()

    return jsonify({'success': True, 'codigo': codigo, 'newData': row})


@bp.route('/api/cotizacion/accion', methods=['POST'])
@login_required
def api_cotizacion_accion():
    """Mueve la petición por el flujo: enviar_validacion, adjuntar_correo,
    validar, cerrar (y revertir solo admin)."""
    if not _puede_cotizaciones():
        return jsonify({'error': 'No tienes el módulo Cotizaciones en tu perfil.'}), 403
    proy = _proy_coti()
    if not proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe.'}), 404

    data = request.get_json(silent=True) or {}
    key = str(data.get('key') or '').strip()
    accion = str(data.get('accion') or '').strip().lower()
    if not key or accion not in ('enviar_validacion', 'adjuntar_correo', 'validar', 'cerrar', 'revertir'):
        return jsonify({'error': 'Datos incompletos o acción no válida.'}), 400

    fila = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=key).first()
    if not fila:
        return jsonify({'error': 'La petición no existe.'}), 404
    try:
        row = json.loads(fila.data_json or '{}')
    except Exception:
        row = {}
    if not _es_peticion(row):
        return jsonify({'error': 'Este registro no pertenece al flujo de peticiones.'}), 409

    estado = _estado_peticion(row)
    usuario_actual = session.get('username') or 'Desconocido'
    now = ahora_peru().strftime('%Y-%m-%d %H:%M:%S')
    row['INTERACCION'] = usuario_actual

    if accion == 'enviar_validacion':
        if estado != COTI_EST_PENDIENTE:
            return jsonify({'error': 'Solo se envía a Validación desde estado Pendiente.'}), 409
        coti_num = str(row.get('N° COTIZACION') or '').strip()
        if not coti_num:
            return jsonify({'error': 'Crea la cotización y anota su N° antes de enviar a Validación.'}), 400
        row['ESTADO'] = COTI_EST_VALIDACION
        row['ENVIADO POR'] = usuario_actual
        row['FECHA ENVIO VALIDACION'] = now

    elif accion == 'adjuntar_correo':
        if estado != COTI_EST_VALIDACION:
            return jsonify({'error': 'Esta petición no está en Validación.'}), 409
        correo = str(data.get('correo') or '').strip()
        if not correo:
            return jsonify({'error': 'Adjunta primero el correo de validación.'}), 400
        row['CORREO DE VALIDACION'] = correo
        fval = str(data.get('fecha_validacion') or '').strip().replace('T', ' ')
        if fval:
            row['FECHA DE VALIDACION'] = fval
        if str(data.get('comentarios') or '').strip():
            row['COMENTARIOS VALIDACION'] = str(data.get('comentarios') or '').strip()

    elif accion in ('validar', 'cerrar'):
        if estado != COTI_EST_VALIDACION:
            return jsonify({'error': 'Esta petición no está en Validación.'}), 409
        correo = str(data.get('correo') or row.get('CORREO DE VALIDACION') or '').strip()
        fecha_val = str(data.get('fecha_validacion') or row.get('FECHA DE VALIDACION') or '').strip().replace('T', ' ')
        if not correo:
            return jsonify({'error': 'Adjunta el correo de validación del cliente.'}), 400
        if not fecha_val:
            return jsonify({'error': 'Ingresa la fecha y hora de validación.'}), 400
        row['CORREO DE VALIDACION'] = correo
        row['FECHA DE VALIDACION'] = fecha_val
        coment = str(data.get('comentarios') or '').strip()
        if coment:
            row['COMENTARIOS VALIDACION'] = coment
        row['ESTADO'] = COTI_EST_VALIDADO if accion == 'validar' else COTI_EST_CERRADO
        if accion == 'validar':
            row['VALIDADO POR'] = usuario_actual
        else:
            row['CERRADO POR'] = usuario_actual

    elif accion == 'revertir':
        if (session.get('rol') or '').strip().lower() not in ('zeno', 'suport', 'admin'):
            return jsonify({'error': 'No tienes permisos para revertir estados.'}), 403
        if estado == COTI_EST_VALIDACION:
            row['ESTADO'] = COTI_EST_PENDIENTE
        elif estado == COTI_EST_VALIDADO:
            row['ESTADO'] = COTI_EST_VALIDACION
        elif estado == COTI_EST_CERRADO:
            row['ESTADO'] = COTI_EST_VALIDACION
        else:
            return jsonify({'error': 'No se puede revertir desde este estado.'}), 400

    fila.data_json = json.dumps(row, ensure_ascii=False)
    fila.key_value = key
    db.session.commit()
    return jsonify({'success': True, 'estado': row['ESTADO'], 'newData': row})


@bp.route('/api/cotizacion/subir_correo', methods=['POST'])
@login_required
def api_cotizacion_subir_correo():
    """Guarda el correo de validación del cliente (adjunto de la hoja Validación)."""
    if not _puede_cotizaciones():
        return jsonify({'error': 'No tienes el módulo Cotizaciones en tu perfil.'}), 403
    proy = _proy_coti()
    if not proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe.'}), 404

    key = (request.form.get('key') or '').strip()
    file = request.files.get('correo')
    if not key or not file:
        return jsonify({'error': 'Falta la petición o el archivo.'}), 400
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in COTI_EXT_CORREO:
        return jsonify({'error': 'Tipo de archivo no permitido (%s).' % (ext or 'sin extensión')}), 400

    nombre = 'correo_validacion' + ext
    ruta = os.path.join(_folder_coti(proy.id, key), secure_filename(nombre))
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
    except Exception:
        return jsonify({'error': 'No se pudo guardar el archivo.'}), 500
    try:
        file.save(ruta)
    except Exception:
        return jsonify({'error': 'No se pudo guardar el archivo.'}), 500

    return jsonify({'success': True,
                    'url': '/api/cotizacion/correo/%d/%s/%s?v=%d'
                           % (proy.id, key, secure_filename(nombre), int(time.time()))})


@bp.route('/api/cotizacion/correo/<int:pid>/<path:key>/<path:nombre>')
@login_required
def api_cotizacion_correo(pid, key, nombre):
    """Sirve el archivo del correo de validación adjuntado."""
    proy = db.session.get(Proyecto, pid)
    if not proy or (proy.nombre or '').strip() != 'Cotizaciones':
        abort(404)
    carpeta = _folder_coti(pid, key)
    ruta = os.path.join(carpeta, secure_filename(nombre))
    if not os.path.isfile(ruta):
        abort(404)
    return send_from_directory(os.path.dirname(ruta), os.path.basename(ruta))