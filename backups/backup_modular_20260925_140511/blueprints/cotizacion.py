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
            'fecha': cot.fecha_generacion.strftime('%d/%m/%Y') if cot.fecha_generacion else ''
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
        'fecha': c.fecha_generacion.strftime('%d/%m/%Y') if c.fecha_generacion else '',
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
            items=items
        )
    except Exception as e:
        return jsonify({'error': f'Error al generar PDF: {str(e)}'}), 500
    from flask import make_response
    resp = make_response(pdf_bytes)
    safe_num = numero.replace('/', '-').replace(' ', '_') or 'cotizacion'
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Cotizacion_{safe_num}.pdf'
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
            items=items
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
                fecha=datetime.now().strftime('%d/%m/%Y'),
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