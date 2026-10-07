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


def _split_wos(valor):
    """NUMERO WO admite 0, 1 o varios WO declarados.

    Se guardan en una sola cadena separados por coma (también se aceptan
    punto y coma, '|' o salto de línea al pegar varios de golpe).
    Devuelve la lista normalizada, vacía si no hay ninguno.
    """
    texto = str(valor or '').strip()
    if not texto:
        return []
    return [w.strip() for w in re.split(r'[,;\n\r|]+', texto) if w.strip()]



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
        # Un registro puede declarar varios WO: se asocia a CADA uno de ellos,
        # para que la misma cotización (una sola) se vea en la pestaña Cotización
        # de todos los WO que cubre.
        wos = _split_wos(d.get('NUMERO WO', ''))
        if klow not in [w.lower() for w in wos]:
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
            # Todos los WO declarados por la cotización (no solo el coincidente)
            'wos': ', '.join(wos),
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
                # El registro puede declarar varios WO: el PDF los lista. Si la
                # cadena es larga se muestra el primero con el conteo para no
                # desbordar el campo "ticket".
                _wos_pdf = _split_wos(d.get('NUMERO WO', ''))
                numero_wo = ', '.join(_wos_pdf)
                if len(numero_wo) > 60 and len(_wos_pdf) > 1:
                    numero_wo = f'{_wos_pdf[0]} (+{len(_wos_pdf) - 1} WOs)'
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


@bp.route('/api/cotizacion/items_template', methods=['GET'])
@login_required
def api_cotizacion_items_template():
    """Genera y descarga una plantilla Excel con las columnas de items de cotización formato Cobra."""
    import io as _io
    # Columnas exactas solicitadas
    cols = ['CORRELATIVO', 'TIPO', 'TEXTO EXPLICATIVO', 'UND', 'CANTIDAD', 'VALOR UNITARIO', 'FEE %', 'VALOR TOTAL', 'COMENTARIOS']
    tipos_validos = ['REEMBOLSABLE', 'LPU']
    und_validos = ['Glb', 'Und', 'm', 'm2', 'Hr', 'Día', 'Mes', 'Viaje', 'Km']
    ejemplo = {
        'CORRELATIVO': 1,
        'TIPO': 'LPU',
        'TEXTO EXPLICATIVO': 'Descripción del trabajo realizado',
        'UND': 'Glb',
        'CANTIDAD': 1,
        'VALOR UNITARIO': 100.00,
        'FEE %': 0,
        'VALOR TOTAL': 100.00,
        'COMENTARIOS': 'Comentario opcional',
    }
    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df = pd.DataFrame([ejemplo], columns=cols)
        df.to_excel(writer, index=False, sheet_name='Items')
        ws = writer.sheets['Items']
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        try:
            from openpyxl.styles import PatternFill, Font, Alignment
            from openpyxl.utils import get_column_letter
            from openpyxl.worksheet.datavalidation import DataValidation
            hdr_fill = PatternFill(start_color='1A73E8', end_color='1A73E8', fill_type='solid')
            hdr_font = Font(bold=True, color='FFFFFF', size=10)
            for idx, col_name in enumerate(cols, 1):
                cell = ws.cell(row=1, column=idx)
                cell.fill = hdr_fill
                cell.font = hdr_font
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            # Validación de TIPO (col B)
            dv_tipo = DataValidation(type='list', formula1='"' + ','.join(tipos_validos) + '"', allow_blank=True, showErrorMessage=True)
            dv_tipo.error = 'Elige REEMBOLSABLE o LPU'
            dv_tipo.errorTitle = 'Tipo inválido'
            ws.add_data_validation(dv_tipo)
            dv_tipo.add('B2:B1000')
            # Validación de UND (col D)
            dv_und = DataValidation(type='list', formula1='"' + ','.join(und_validos) + '"', allow_blank=True, showErrorMessage=False)
            ws.add_data_validation(dv_und)
            dv_und.add('D2:D1000')
            # Ancho de columnas: CORRELATIVO | TIPO | TEXTO EXPLICATIVO | UND | CANTIDAD | VALOR UNITARIO | FEE % | VALOR TOTAL | COMENTARIOS
            anchos = [14, 16, 48, 12, 12, 18, 10, 16, 36]
            for idx, ancho in enumerate(anchos, 1):
                ws.column_dimensions[get_column_letter(idx)].width = ancho
        except Exception:
            pass
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = 'attachment; filename=Plantilla_Items_Cotizacion.xlsx'
    return resp


@bp.route('/api/cotizacion/items_import', methods=['POST'])
@login_required
def api_cotizacion_items_import():
    """Recibe un Excel con items de cotización y devuelve la lista parseada como JSON."""
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No se recibió archivo'}), 400
    fname = (f.filename or '').lower()
    try:
        if fname.endswith('.csv'):
            import io as _io
            raw = f.read()
            # Intentar UTF-8 primero, luego latin-1 como fallback
            for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
                try:
                    df = pd.read_csv(_io.BytesIO(raw), encoding=enc, dtype=str)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                df = pd.read_csv(_io.BytesIO(raw), encoding='latin-1', dtype=str)
        else:
            import io as _io
            df = pd.read_excel(_io.BytesIO(f.read()), dtype=str)
    except Exception as e:
        return jsonify({'error': f'No se pudo leer el archivo: {str(e)}'}), 400

    df.columns = [str(c).strip().upper() for c in df.columns]
    df = df.where(pd.notna(df), '')

    # Mapas de sinónimos de columnas
    MAP = {
        'correlativo': ['CORRELATIVO', 'CORR', 'N° ITEM', 'N°ITEM', 'ITEM'],
        'TIPO': ['TIPO'],
        'texto': ['TEXTO EXPLICATIVO', 'TEXTO', 'DESCRIPCION', 'DESCRIPCIÓN', 'DETALLE'],
        'und': ['UND', 'UNIDAD', 'UNID'],
        'cantidad': ['CANTIDAD', 'CANT'],
        'valor_unitario': ['VALOR UNITARIO', 'VALOR_UNITARIO', 'V. UNITARIO', 'PRECIO', 'PRECIO UNITARIO'],
        'fee': ['FEE %', 'FEE', 'FEE%', 'FEE PORCENTAJE'],
        'comentarios': ['COMENTARIOS', 'COMENTARIO', 'NOTAS', 'NOTA'],
    }

    def _col(synonyms):
        for s in synonyms:
            if s.upper() in df.columns:
                return s.upper()
        return None

    col_corr = _col(MAP['correlativo'])
    col_tipo = _col(MAP['TIPO'])
    col_texto = _col(MAP['texto'])
    col_und = _col(MAP['und'])
    col_cant = _col(MAP['cantidad'])
    col_vu = _col(MAP['valor_unitario'])
    col_fee = _col(MAP['fee'])
    col_com = _col(MAP['comentarios'])

    items = []
    for _, row in df.iterrows():
        texto = str(row[col_texto] if col_texto else '').strip()
        cant_raw = str(row[col_cant] if col_cant else '').strip()
        vu_raw = str(row[col_vu] if col_vu else '').strip()
        # Saltar filas completamente vacías
        if not texto and not cant_raw and not vu_raw:
            continue
        tipo_raw = str(row[col_tipo] if col_tipo else '').strip().upper()
        tipo = tipo_raw if tipo_raw in ('REEMBOLSABLE', 'LPU') else ''
        und = str(row[col_und] if col_und else '').strip()
        comentarios = str(row[col_com] if col_com else '').strip()
        try:
            cant = float(cant_raw.replace(',', '.')) if cant_raw else None
        except (ValueError, TypeError):
            cant = None
        try:
            vu = float(vu_raw.replace(',', '.')) if vu_raw else None
        except (ValueError, TypeError):
            vu = None
        # FEE: leer desde columna si existe; fallback automático por tipo
        fee_raw = str(row[col_fee] if col_fee else '').strip() if col_fee else ''
        try:
            fee = float(fee_raw.replace(',', '.').replace('%', '')) if fee_raw else None
        except (ValueError, TypeError):
            fee = None
        if fee is None:
            fee = 5 if tipo == 'REEMBOLSABLE' else 0
        vt = None
        if cant is not None and vu is not None:
            vt = round(cant * vu * (1 + fee / 100), 2)
        corr_raw = str(row[col_corr] if col_corr else '').strip()
        item = {
            'correlativo': corr_raw,
            'tipo': tipo,
            'texto': texto,
            'und': und,
            'cantidad': str(cant) if cant is not None else '',
            'valor_unitario': str(vu) if vu is not None else '',
            'fee': str(int(fee)) if fee == int(fee) else str(fee),
            'valor_total': str(vt) if vt is not None else '',
            'comentarios': comentarios,
        }
        items.append(item)
    if not items:
        return jsonify({'error': 'No se encontraron filas con datos. Usa la plantilla descargable como referencia.'}), 400
    return jsonify({'items': items, 'total': len(items)})


# ─────────────────────────────────────────────────────────────────────────────
# Flujo de estados del módulo Cotizaciones (4 pestañas):
#   1. Registro (Pdt. Cotización) -> al "Generar" viaja a ->
#   2. Cliente (En Aprobación) -> Aprobado -> 3. Atendido
#                              -> Rechazado (con motivo) -> vuelve a 1. Registro
#                              -> Cancelado (con motivo) -> 4. Cancelado/Anulada
#   Desde 1. Registro también se puede Rechazar (queda en Registro con motivo)
#   o Cancelar de plano (-> 4).
# El estado vive en la columna ESTADO COTIZACION (misma que se edita en línea).
# ─────────────────────────────────────────────────────────────────────────────
ESTADO_NUEVO = 'Pdt. Cotización'
ESTADO_COTIZADO = 'Cotizado'
ESTADO_APROBACION = 'En Aprobación'
ESTADO_ATENDIDO = 'Atendido'
ESTADO_CANCELADO = 'Cancelado'
ESTADOS_FLUJO = (ESTADO_NUEVO, ESTADO_COTIZADO, ESTADO_APROBACION, ESTADO_ATENDIDO)

# Estados viejos que la columna ya usa (siguen siendo válidos para no romper
# filas existentes ni la edición en línea validada por rows.py).
ESTADOS_LEGADO = ('En proceso', 'Observado', 'Rechazado', 'Validado', 'Cancelado')

# A qué pestaña cae cada valor guardado. Lo que no esté listado cae en la
# pestaña 1 (Registro) para que ninguna fila desaparezca de la vista.
#   - 'Validado' (viejo) -> Atendido
#   - 'Observado'/'Rechazado'/'En proceso' -> Registro
MAPA_PESTANIA = {
    ESTADO_ATENDIDO.lower(): 'atendido',
    'validado': 'atendido',
    # La pestaña intermedia "Cotización" se eliminó: lo generado (incluso el
    # estado legado 'Cotizado') se muestra directamente en la pestaña Cliente.
    ESTADO_COTIZADO.lower(): 'cliente',
    ESTADO_APROBACION.lower(): 'cliente',
    'en aprobacion': 'cliente',
    ESTADO_CANCELADO.lower(): 'cancelado',
    'anulado': 'cancelado',
    'anulada': 'cancelado',
}


def _cot_estado_guardado(row):
    """Valor crudo guardado en la columna ESTADO COTIZACION."""
    return str((row or {}).get('ESTADO COTIZACION') or '').strip()


def _cot_pestania(row):
    """Pestaña (1..4) a la que pertenece la fila según su estado."""
    v = _cot_estado_guardado(row).lower()
    return MAPA_PESTANIA.get(v, 'registro')


def _cot_proyecto():
    return Proyecto.query.filter_by(nombre='Cotizaciones').first()


def _cot_puede_gestionar():
    return _puede_cotizaciones()


def _cot_folder(pid, key):
    BASE = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(BASE, 'static', 'evidencia', str(pid),
                        secure_filename(str(key)))


EXT_CORREO_OK = ('.pdf', '.msg', '.eml', '.doc', '.docx',
                 '.jpg', '.jpeg', '.png', '.webp')


@bp.route('/api/cotizacion/accion', methods=['POST'])
@login_required
def api_cotizacion_accion():
    """Mueve la cotización por el flujo de 4 pestañas.

    acciones:
      generar              Pdt. Cotización -> En Aprobación (viaja a Cliente)
      conformar_aprobacion En Aprobación   -> Atendido (fecha + correo .msg + comentario)
      rechazar             Cliente/Registro -> Pdt. Cotización (fecha + motivo)
      cancelar             Cliente/Registro -> Cancelado (fecha + motivo)
      revertir             un paso atrás (solo admin)
    """
    if not _cot_puede_gestionar():
        return jsonify({'error': 'No tienes permisos para gestionar cotizaciones.'}), 403
    proy = _cot_proyecto()
    if not proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe.'}), 404

    data = request.get_json(silent=True) or {}
    key = str(data.get('key') or '').strip()
    accion = str(data.get('accion') or '').strip().lower()
    if accion == 'rechazar_registro':  # alias legado del frontend
        accion = 'rechazar'
    if accion == 'aprobar':
        accion = 'conformar_aprobacion'
    if not key or accion not in ('generar', 'enviar', 'conformar_aprobacion',
                                 'revertir', 'rechazar', 'cancelar'):
        return jsonify({'error': 'Datos incompletos o acción no válida.'}), 400

    fila = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=key).first()
    if not fila:
        return jsonify({'error': 'La cotización no existe.'}), 404
    try:
        row = json.loads(fila.data_json or '{}')
    except Exception:
        row = {}

    pestania = _cot_pestania(row)
    ahora = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    usuario = session.get('username') or 'Desconocido'

    if accion == 'generar':
        # Se genera la cotización (PDF) y viaja DIRECTO a la pestaña Cliente
        # (queda a la espera de la conformidad del cliente). Idempotente: si ya
        # está en Cliente con cotización generada, no falla.
        if pestania == 'cliente':
            return jsonify({'success': True,
                            'estado': row.get('ESTADO COTIZACION'),
                            'pestania': 'cliente',
                            'newData': row})
        if pestania != 'registro':
            return jsonify({'error': 'Solo se puede generar una cotización que esté en "Pdt. Cotización".'}), 409
        row['ESTADO COTIZACION'] = ESTADO_APROBACION
        row['FECHA COTIZADO'] = ahora
        row['COTIZADO POR'] = usuario
        row['FECHA ENVIO CLIENTE'] = ahora
        row['ENVIADO POR'] = usuario

    elif accion == 'enviar':
        # Compatibilidad: si la fila quedó en estado legado 'Cotizado', enviarla
        # la lleva a Cliente igual que "generar".
        if pestania == 'cliente':
            return jsonify({'success': True,
                            'estado': row.get('ESTADO COTIZACION'),
                            'pestania': 'cliente',
                            'newData': row})
        return jsonify({'error': 'Ya no hay "Enviar": al generar, la cotización viaja directo a Cliente.'}), 409

    elif accion == 'conformar_aprobacion':
        if pestania != 'cliente':
            return jsonify({'error': 'La aprobación solo aplica a una cotización "En Aprobación" (pestaña Cliente).'}), 409
        row['ESTADO COTIZACION'] = ESTADO_ATENDIDO
        row['FECHA APROBACION'] = str(data.get('fecha_aprobacion') or '').strip() or ahora
        row['APROBADO POR'] = usuario
        row['COMENTARIO APROBACION'] = str(data.get('comentario') or '').strip()
        adj = str(data.get('adjunto_correo') or '').strip()
        if adj:
            row['ADJUNTO CORREO CLIENTE'] = adj

    elif accion == 'rechazar':
        # El cliente observa/rechaza y la solicitud regresa a Pdt. Cotización
        # (pestaña 1) para que quien la pidió la corrija y reenvíe. También
        # sirve en Registro: el pedido queda rechazado con su motivo.
        if pestania not in ('registro', 'cliente'):
            return jsonify({'error': 'Solo se puede rechazar desde Registro o Cliente.'}), 409
        motivo = str(data.get('motivo') or data.get('motivo_rechazo') or '').strip()
        if not motivo:
            return jsonify({'error': 'El motivo del rechazo es obligatorio.'}), 400
        row['ESTADO COTIZACION'] = ESTADO_NUEVO
        row['FECHA RECHAZO'] = str(data.get('fecha_rechazo') or '').strip() or ahora
        row['RECHAZADO POR'] = usuario
        row['MOTIVO RECHAZO'] = motivo
        # Deja registrada la última decisión del cliente sin necesidad de columna
        comentarios = str(row.get('OBSERVACIONES', '') or '').strip()
        nota = '[Rechazo %s · %s] %s' % (row['FECHA RECHAZO'], usuario, motivo)
        row['OBSERVACIONES'] = (nota if not comentarios else (comentarios + '\n' + nota))[:2000]

    elif accion == 'cancelar':
        # Cancelado de plano: ya no sigue el flujo, va a la pestaña
        # Cancelado/Anulada (historial).
        if pestania in ('cancelado', 'atendido'):
            return jsonify({'error': 'No se puede cancelar una cotización atendida o ya cancelada.'}), 409
        motivo = str(data.get('motivo') or data.get('motivo_cancel') or '').strip()
        if not motivo:
            return jsonify({'error': 'El motivo de la cancelación es obligatorio.'}), 400
        row['ESTADO COTIZACION'] = ESTADO_CANCELADO
        row['FECHA CANCELACION'] = str(data.get('fecha_cancelacion') or '').strip() or ahora
        row['CANCELADO POR'] = usuario
        row['MOTIVO CANCELACION'] = motivo
        comentarios = str(row.get('OBSERVACIONES', '') or '').strip()
        nota = '[Cancelación %s · %s] %s' % (row['FECHA CANCELACION'], usuario, motivo)
        row['OBSERVACIONES'] = (nota if not comentarios else (comentarios + '\n' + nota))[:2000]

    elif accion == 'revertir':
        rol = str(session.get('rol') or '').strip().lower()
        if rol not in ('zeno', 'suport', 'admin'):
            return jsonify({'error': 'No tienes permisos para revertir estados.'}), 403
        if pestania == 'cliente':
            row['ESTADO COTIZACION'] = ESTADO_NUEVO
        elif pestania == 'atendido':
            row['ESTADO COTIZACION'] = ESTADO_APROBACION
        elif pestania == 'cancelado':
            row['ESTADO COTIZACION'] = ESTADO_NUEVO
        else:
            return jsonify({'error': 'No se puede revertir desde "Pdt. Cotización".'}), 400

    fila.data_json = safe_json_dumps(row)
    db.session.commit()
    return jsonify({'success': True,
                    'estado': row.get('ESTADO COTIZACION'),
                    'pestania': _cot_pestania(row),
                    'newData': row})


@bp.route('/api/cotizacion/subir_correo', methods=['POST'])
@login_required
def api_cotizacion_subir_correo():
    """Sube la evidencia del correo del cliente (.msg/.pdf/captura) y devuelve su URL."""
    if not _cot_puede_gestionar():
        return jsonify({'error': 'No tienes permisos para subir adjuntos.'}), 403
    proy = _cot_proyecto()
    if not proy:
        return jsonify({'error': 'Módulo Cotizaciones no existe.'}), 404

    key = (request.form.get('key') or '').strip()
    file = request.files.get('adjunto')
    if not key:
        return jsonify({'error': 'Falta la clave del registro.'}), 400
    if file is None or not file.filename:
        return jsonify({'error': 'No se recibió ningún archivo.'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in EXT_CORREO_OK:
        return jsonify({'error': 'Formato no permitido. Usa .msg, .pdf, .doc, JPG, PNG o WEBP.'}), 400

    key = secure_filename(key)
    nombre = 'correo_aprob_%d%s' % (int(time.time()), ext)
    fd, ruta_tmp = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        file.save(ruta_tmp)
        if evidencia_usa_b2():
            b2_cliente().upload_file(ruta_tmp, current_app.config['B2_BUCKET'],
                                     '%s/%s' % (key, nombre))
        else:
            folder = _cot_folder(proy.id, key)
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, nombre), 'wb') as fh, \
                 open(ruta_tmp, 'rb') as src:
                fh.write(src.read())
        url = '/api/cotizacion/correo/%d/%s/%s?v=%d' % (
            proy.id, key, nombre, int(time.time()))
        return jsonify({'success': True, 'url': url})
    finally:
        if os.path.exists(ruta_tmp):
            try:
                os.remove(ruta_tmp)
            except Exception:
                pass


@bp.route('/api/cotizacion/correo/<int:pid>/<path:key>/<path:nombre>')
@login_required
def api_cotizacion_correo(pid, key, nombre):
    """Sirve la evidencia del correo del cliente."""
    if not _cot_puede_gestionar():
        return jsonify({'error': 'No autorizado.'}), 403
    proy = _cot_proyecto()
    if not proy or int(pid) != int(proy.id):
        return jsonify({'error': 'No encontrado'}), 404
    nombre = os.path.basename(secure_filename(nombre))
    if evidencia_usa_b2():
        try:
            obj = b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'],
                                          Key='%s/%s' % (key, nombre))
            resp = Response(obj['Body'].read(),
                            mimetype=mimetypes.guess_type(nombre)[0] or 'application/octet-stream')
            resp.headers['Cache-Control'] = 'private, max-age=604800, immutable'
            return resp
        except Exception:
            return jsonify({'error': 'No encontrado'}), 404
    folder = _cot_folder(pid, key)
    ruta = os.path.join(folder, nombre)
    if not os.path.exists(ruta):
        return jsonify({'error': 'No encontrado'}), 404
    return send_from_directory(folder, nombre, max_age=604800)