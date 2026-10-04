# -*- coding: utf-8 -*-
import os, io, re, json, time, glob, zipfile, gzip, mimetypes, tempfile
import urllib.request, urllib.parse
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


bp = Blueprint('wo', __name__)



@bp.route('/api/combustible/por_wo', methods=['GET'])
@login_required
def api_combustible_por_wo():
    """Movimientos de Combustible (INGRESO/GASTO) asociados al WO (campo WO NUMBER)."""
    wo = request.args.get('wo', '').strip()
    if not wo:
        return jsonify({'movimientos': []})
    try:
        comb_proy = Proyecto.query.filter_by(nombre='Combustible').first()
        if not comb_proy:
            return jsonify({'movimientos': []})
        rows = []
        for r in NucleusData.query.filter_by(proyecto_id=comb_proy.id).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            if str(d.get('WO NUMBER', '')).strip() != wo:
                continue
            d['_key'] = r.key_value
            rows.append(d)
        rows.sort(key=lambda d: (str(d.get('FECHA', '') or ''), str(d.get('_key', '') or '')))
        return jsonify({'movimientos': rows})
    except Exception:
        return jsonify({'movimientos': []})


@bp.route('/api/wo/meta', methods=['GET'])
@login_required
def api_wo_meta():
    pid = session.get('current_proyecto_id')
    proy_obj = db.session.get(Proyecto, pid) if pid else None
    proy_nombre = proy_obj.nombre.strip() if proy_obj and proy_obj.nombre else ''
    try:
        # Opciones de SERVICIO (configurables por proyecto)
        scfg = AppConfig.query.filter_by(proyecto_id=pid, clave='servicio_opciones').first()
        if scfg:
            try:
                servicios = json.loads(scfg.valor)
                if not isinstance(servicios, list):
                    servicios = []
            except Exception:
                servicios = []
        else:
            servicios = ['PREVENTIVO', 'CORRECTIVO', 'PREDICTIVO', 'ABASTECIMIENTO DE COMBUSTIBLE',
                         'ADICIONALES', 'CORTE PROGRAMADO', 'TRABAJO PROGRAMADO']

        # Técnicos: se unen DOS fuentes para que el desplegable nunca quede vacío:
        #  (1) tabla `tecnicos` declarada en el panel de administración — proyecto
        #      actual y su hermano FLM / FLM - ENTEL (comparten el mismo equipo);
        #  (2) Dataper (histórico): técnicos ACTIVOS cuyo PROYECTO coincida con la
        #      familia del proyecto actual (FLM y FLM - ENTEL cuentan como la misma).
        # Se deduplica por nombre; si una fuente trae la contrata y la otra no, se conserva.
        _tec_map = {}

        def _add_tec(nombre, contrata):
            nom = str(nombre or '').strip()
            if not nom:
                return
            k = nom.lower()
            reg = _tec_map.get(k)
            if reg is None:
                _tec_map[k] = {'nombre': nom, 'contrata': str(contrata or '').strip()}
            elif not reg['contrata'] and str(contrata or '').strip():
                reg['contrata'] = str(contrata or '').strip()

        # (1) Declarados en el admin (proyecto actual + hermano FLM)
        _tec_pids = [pid] if pid else []
        _hermano = _flm_hermano_id(pid) if pid else None
        if _hermano:
            _tec_pids.append(_hermano)
        if _tec_pids:
            for t in Tecnico.query.filter(Tecnico.proyecto_id.in_(_tec_pids)).all():
                _add_tec(t.nombre, t.contrata)
        elif not pid:
            for t in Tecnico.query.all():
                _add_tec(t.nombre, t.contrata)

        # (2) Dataper: cargar técnicos activos (o sin ESTADO definido).
        # Se incluyen registros cuyo ESTADO sea 'ACTIVO' o esté vacío/null.
        # Registros con ESTADO='CESADO' u otro valor se excluyen.
        import logging as _log
        dataper = Proyecto.query.filter_by(nombre='Dataper').first()
        if dataper:
            dataper_rows = NucleusData.query.filter_by(proyecto_id=dataper.id).all()
            _log.warning(f'[WO-META] Dataper id={dataper.id} filas={len(dataper_rows)}')
            _incluidos = 0
            for r in dataper_rows:
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                est = str(d.get('ESTADO') or '').strip().upper()
                # Excluir solo si el campo existe Y tiene un valor distinto a ACTIVO
                if est and est != 'ACTIVO':
                    continue
                _add_tec(d.get('TECNICO'), d.get('CONTRATA'))
                _incluidos += 1
            _log.warning(f'[WO-META] técnicos incluidos desde Dataper={_incluidos}, total_map={len(_tec_map)}')

        tecnicos = sorted(_tec_map.values(), key=lambda x: x['nombre'])

        # Materiales desde MATERIAL, filtrados por el PROYECTO actual
        materiales = []
        material_proy = Proyecto.query.filter_by(nombre='Material').first()
        if material_proy:
            seen = set()
            for r in NucleusData.query.filter_by(proyecto_id=material_proy.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                pr = str(d.get('PROYECTO') or '').strip()
                # FLM/PEXT/FLM - ENTEL se tratan como el mismo mundo: si el
                # proyecto actual es FLM - ENTEL, acepta material etiquetado
                # 'FLM' o 'PEXT' (filas migradas) y viceversa.
                if proy_nombre:
                    de_mismo_mundo = set()
                    if proy_nombre.upper() in ('FLM', 'FLM - ENTEL', 'PEXT'):
                        de_mismo_mundo = {'FLM', 'FLM - ENTEL', 'PEXT'}
                    if pr and pr.upper() not in de_mismo_mundo and pr.upper() != proy_nombre.upper():
                        continue
                desc = str(d.get('DESCRIPCION_MATERIAL') or '').strip()
                if not desc or desc in seen:
                    continue
                seen.add(desc)
                materiales.append({
                    'codigo': str(d.get('COD_MATERIAL') or r.key_value or '').strip(),
                    'descripcion': desc,
                    'tipo': str(d.get('TIPO') or '').strip(),
                    'um': str(d.get('UM') or '').strip()
                })
        materiales.sort(key=lambda x: x['descripcion'])

        return jsonify({'success': True, 'servicios': servicios, 'tecnicos': tecnicos,
                        'materiales': materiales, 'proyecto': proy_nombre})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


_OPCIONES_TTL = 120.0
_opciones_cache = {'ts': 0.0, 'data': None}


def invalidar_opciones_cache():
    """Se llama tras escribir filas para que las listas de opciones se recalculen."""
    _opciones_cache['ts'] = 0.0
    _opciones_cache['data'] = None


@bp.route('/api/detalle/opciones', methods=['GET'])
@login_required
def api_detalle_opciones():
    try:
        # Cache en memoria: este endpoint recorre SITE + Site Name + FLM + PEXT
        # (decenas de miles de filas con json.loads) y se pide en CADA carga de FLM.
        if _opciones_cache['data'] is not None and (time.time() - _opciones_cache['ts']) < _OPCIONES_TTL:
            return jsonify(_opciones_cache['data'])
        # Agrega valores válidos para los 5 campos del Detalle (solo admin los edita):
        # NOMBRE DE SITE, DEPARTAMENTO, PRIORIDAD DEL SITE, PROVINCIA, DISTRITO.
        # Se recolectan desde SITE (maestro) + Site Name + WOs (FLM/PEXT) para cubrir casos históricos.
        nombres_set = set()
        dept_set = set()
        prov_set = set()
        dist_set = set()
        prio_set = set()
        dept_prov_map = {}
        prov_dist_map = {}
        site_geo_map = {}
        def add_norm(s): return str(s or '').strip()
        # SITE maestro (id 9) y Site Name (id 5) + FLM/PEXT como respaldo
        for nombre_proy in ('SITE', 'Site Name', 'FLM', 'FLM - ENTEL', 'PEXT'):
            proy = Proyecto.query.filter_by(nombre=nombre_proy).first()
            if not proy:
                continue
            for r in NucleusData.query.filter_by(proyecto_id=proy.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                # Normalizar claves para búsqueda insensible
                low_map = {str(k).strip().lower(): v for k, v in d.items()}
                # Nombre de Site
                for k in ('nombre de site', 'nombre', 'codigo site'):
                    v = add_norm(low_map.get(k))
                    if v and k in ('nombre de site', 'nombre'):
                        nombres_set.add(v)
                        # Para SITE, guardar geo del site
                        if nombre_proy == 'SITE':
                            dept = add_norm(low_map.get('departamento'))
                            prov = add_norm(low_map.get('provincia'))
                            dist = add_norm(low_map.get('distrito'))
                            prio = add_norm(low_map.get('prioridad'))
                            if dept: dept_set.add(dept)
                            if prov: prov_set.add(prov)
                            if dist: dist_set.add(dist)
                            if prio: prio_set.add(prio)
                            if dept and prov:
                                dept_prov_map.setdefault(dept, set()).add(prov)
                            if prov and dist:
                                prov_dist_map.setdefault(prov, set()).add(dist)
                            site_geo_map[v] = {'departamento': dept, 'provincia': prov, 'distrito': dist, 'prioridad': prio}
                        # Site Name no tiene geo detallado, pero igual agrega nombre
                    elif v and k == 'codigo site' and nombre_proy in ('FLM', 'FLM - ENTEL', 'PEXT'):
                        # No usar código como nombre, solo como fallback si falta nombre
                        pass
                if nombre_proy in ('FLM', 'FLM - ENTEL', 'PEXT'):
                    for k in ('departamento', 'provincia', 'distrito', 'prioridad del site'):
                        v = add_norm(low_map.get(k))
                        if not v:
                            continue
                        if k == 'departamento': dept_set.add(v)
                        elif k == 'provincia': prov_set.add(v)
                        elif k == 'distrito': dist_set.add(v)
                        elif k == 'prioridad del site': prio_set.add(v)
                    # También mapa geo desde WOs para jerarquía adicional
                    dept = add_norm(low_map.get('departamento'))
                    prov = add_norm(low_map.get('provincia'))
                    dist = add_norm(low_map.get('distrito'))
                    if dept and prov:
                        dept_prov_map.setdefault(dept, set()).add(prov)
                    if prov and dist:
                        prov_dist_map.setdefault(prov, set()).add(dist)
        # Si aún hay pocos departamentos, completar con lista peruana conocida para no bloquear válidos nuevos
        # Prioridad siempre restringida a P0,P0+,P1-P4
        if not prio_set:
            prio_set = {'P0', 'P0+', 'P1', 'P2', 'P3', 'P4'}
        # Convertir sets a listas ordenadas
        def s2l(s): return sorted(s, key=lambda x: x.lower())
        payload = {'success': True,
                   'nombres': s2l(nombres_set),
                   'departamentos': s2l(dept_set),
                   'provincias': s2l(prov_set),
                   'distritos': s2l(dist_set),
                   'prioridades': s2l(prio_set),
                   'dept_prov_map': {k: s2l(v) for k, v in dept_prov_map.items()},
                   'prov_dist_map': {k: s2l(v) for k, v in prov_dist_map.items()},
                   'site_geo_map': site_geo_map}
        _opciones_cache['data'] = payload
        _opciones_cache['ts'] = time.time()
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/wo/servicios', methods=['POST'])
@login_required
def api_wo_servicios():
    pid = session.get('current_proyecto_id')
    if session.get('rol') not in ['zeno', 'suport', 'supervisor']:
        return jsonify({'error': 'No tienes permisos para editar servicios.'}), 403
    try:
        data = request.json or {}
        opciones = data.get('opciones', [])
        if not isinstance(opciones, list):
            return jsonify({'error': 'Formato inválido'}), 400
        opciones = [str(o).strip() for o in opciones if str(o).strip()]
        scfg = AppConfig.query.filter_by(proyecto_id=pid, clave='servicio_opciones').first()
        if scfg:
            scfg.valor = json.dumps(opciones, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='servicio_opciones', valor=json.dumps(opciones, ensure_ascii=False)))
        db.session.commit()
        return jsonify({'success': True, 'servicios': opciones})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/wo/historial', methods=['GET'])
@login_required
def api_wo_historial():
    # Estado e Historial del WO: solo visible para el personal administrativo/supervisor.
    if str(session.get('rol') or '').strip().lower() not in ('zeno', 'suport', 'supervisor'):
        return jsonify({'error': 'Solo el personal administrativo puede ver el historial.'}), 403
    pid = session.get('current_proyecto_id')
    key_val = (request.args.get('key') or '').strip()
    if not key_val:
        return jsonify({'error': 'Falta el identificador del WO'}), 400
    try:
        rows = (HistorialCambios.query
                .filter_by(proyecto_id=pid, key_value=key_val)
                .order_by(HistorialCambios.fecha.desc(), HistorialCambios.id.desc())
                .all())
        items = [{
            'campo': h.campo_modificado,
            'valor_anterior': h.valor_anterior or '',
            'valor_nuevo': h.valor_nuevo or '',
            'username': h.username,
            # La fecha se guarda en UTC y se convierte a hora de Perú (UTC-5).
            'fecha': (h.fecha - timedelta(hours=5)).isoformat() if h.fecha else None
        } for h in rows]
        return jsonify({'success': True, 'historial': items})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/wo/enviar_aprobacion', methods=['POST'])
@login_required
def api_wo_enviar_aprobacion():
    """Enviar/un-deshacer la aprobación de un WO PEXT/FLM.

    - Gestor envía ('enviar'): marca `_ENVIADO_APROBACION` y bloquea su edición.
    - Admin desbloquea ('desbloquear'): vuelve a permitir la edición tras revisión."""
    rol = str(session.get('rol') or '').strip().lower()
    if rol not in ('contrata', 'gestor', 'supervisor', 'zeno', 'suport'):
        return jsonify({'error': 'No tienes permisos para esta acción.'}), 403
    data = request.json or {}
    pid = session.get('current_proyecto_id')
    key = str(data.get('key') or '').strip()
    accion = str(data.get('accion') or 'enviar').strip().lower()
    if not pid or not key:
        return jsonify({'error': 'Faltan datos.'}), 400
    proy = db.session.get(Proyecto, pid)
    proy_nombre = proy.nombre.strip() if proy and proy.nombre else ''
    if proy_nombre not in ('PEXT', 'FLM', 'FLM - ENTEL'):
        return jsonify({'error': 'Acción solo válida para WOs PEXT/FLM.'}), 400
    if rol in ('contrata', 'gestor'):
        acc = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id'), proyecto_id=pid).first()
        if not acc:
            return jsonify({'error': 'No tienes acceso a este proyecto.'}), 403
    record = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).first()
    if not record:
        return jsonify({'error': 'WO no encontrado.'}), 404
    try:
        d = json.loads(record.data_json or '{}')
    except Exception:
        d = {}
    if accion == 'enviar':
        if str(d.get('_ENVIADO_APROBACION', '')).strip() == '1':
            return jsonify({'error': 'Este WO ya fue enviado a aprobación.'}), 400
        d['_ENVIADO_APROBACION'] = '1'
        d['_APROBACION_FECHA'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        d['_APROBACION_USUARIO'] = session.get('username') or ''
    elif accion == 'desbloquear':
        if rol not in ('zeno', 'suport'):
            return jsonify({'error': 'Solo el administrador puede desbloquear la aprobación.'}), 403
        if str(d.get('_ENVIADO_APROBACION', '')).strip() != '1':
            return jsonify({'error': 'Este WO no está enviado a aprobación.'}), 400
        d['_ENVIADO_APROBACION'] = '0'
        d.pop('_APROBACION_FECHA', None)
        d.pop('_APROBACION_USUARIO', None)
    else:
        return jsonify({'error': 'Acción no válida.'}), 400
    record.data_json = json.dumps(d, ensure_ascii=False)
    # FLM <-> FLM - ENTEL: la aprobación se refleja en el CM espejo del otro proyecto.
    _flm_sync_campos(pid, key, {
        '_ENVIADO_APROBACION': d.get('_ENVIADO_APROBACION', '0'),
        '_APROBACION_FECHA': d.get('_APROBACION_FECHA', ''),
        '_APROBACION_USUARIO': d.get('_APROBACION_USUARIO', ''),
    }, None)
    db.session.commit()
    rows_injected, _ = inject_kpis(pid, [d])
    return jsonify({'success': True, 'newData': rows_injected[0]})


@bp.route('/api/sites')
@login_required
def api_sites():
    """API que devuelve todos los sites con coordenadas válidas para el mapa."""
    proy_site = Proyecto.query.filter_by(nombre='SITE').first()
    if not proy_site:
        return jsonify([])
    sites = []
    for r in NucleusData.query.filter_by(proyecto_id=proy_site.id).all():
        try:
            d = json.loads(r.data_json)
        except Exception:
            continue
        lat_raw = d.get('Latitud (°)', '') or d.get('Latitud', '') or d.get('LATITUD', '')
        lng_raw = d.get('Longitud (°)', '') or d.get('Longitud', '') or d.get('LONGITUD', '')
        try:
            lat = float(str(lat_raw).replace(',', '.').strip())
            lng = float(str(lng_raw).replace(',', '.').strip())
        except Exception:
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        if lat == 0 and lng == 0:
            continue
        site_entry = {
            'codigo': d.get('Código', '') or d.get('Código Site', '') or d.get('Codigo', '') or r.key_value,
            'nombre': d.get('Nombre', '') or d.get('Nombre Site', ''),
            'lat': lat,
            'lng': lng,
            'estado': d.get('Estado', '') or d.get('ESTADO', ''),
            'prioridad': d.get('Prioridad', '') or d.get('PRIORIDAD', ''),
            'contrata': d.get('Contrata', '') or d.get('CONTRATA', ''),
            'departamento': d.get('Departamento', ''),
            'provincia': d.get('Provincia', ''),
            'distrito': d.get('Distrito', ''),
            'direccion': d.get('Dirección', '') or d.get('Direccion', ''),
            'region': d.get('Región', '') or d.get('Region', ''),
            'supervisor': d.get('SUPERVISOR', '') or d.get('Supervisor', ''),
        }
        sites.append(site_entry)
    return jsonify(sites)


@bp.route('/api/site/detalle')
@login_required
def api_site_detalle():
    """Devuelve TODOS los campos de un site (para el panel de detalle del mapa).
    Se carga bajo demanda para no enviar el maestro completo en la lista."""
    codigo = (request.args.get('codigo') or '').strip()
    proy_site = Proyecto.query.filter_by(nombre='SITE').first()
    if not proy_site:
        return jsonify({}), 404
    rec = NucleusData.query.filter_by(proyecto_id=proy_site.id, key_value=codigo).first()
    if not rec:
        return jsonify({'error': 'Site no encontrado.'}), 404
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    return jsonify({k: str(v) for k, v in d.items() if not k.startswith('_')})


@bp.route('/api/wos_flm')
@login_required
def api_wos_flm():
    """Devuelve la lista de números de WO (CMs) del proyecto FLM para autocompletado."""
    proy_flm = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
    if not proy_flm:
        proy_flm = Proyecto.query.filter_by(nombre='FLM').first()
    if not proy_flm:
        return jsonify([])
    # The key_value is the "Número de WO" in FLM
    wos = [r.key_value for r in db.session.query(NucleusData.key_value).filter_by(proyecto_id=proy_flm.id).all()]
    return jsonify(wos)


@bp.route('/api/wo/resolver')
@login_required
def api_wo_resolver():
    """Resuelve a qué proyecto (FLM/PEXT) pertenece un WO por su Número de WO."""
    wo = (request.args.get('wo') or request.args.get('key') or '').strip()
    if not wo:
        return jsonify({'found': False, 'error': 'Falta WO'}), 400
    for nombre in ['FLM - ENTEL', 'FLM', 'PEXT']:
        proy = Proyecto.query.filter_by(nombre=nombre).first()
        if not proy:
            continue
        rec = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=wo).first()
        if rec:
            return jsonify({'found': True, 'proyecto_id': proy.id, 'proyecto_nombre': proy.nombre, 'key': wo})
    return jsonify({'found': False}), 404


# ─────────────────────────────────────────────────────────────────────────────
# AUTIN · fotos del WO leídas desde una PC/unidad montada
#   Estructura esperada:  <RAIZ>\<prefijo><WO NUMBER>\arrive_1.jpg ...
#   La RAIZ se resuelve:  env AUTIN_FOTOS_DIR  >  AppConfig(autin_fotos_dir)  >  <BASE>/fotos_autin
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata

AUTIN_CLAVE = 'autin_fotos_dir'
AUTIN_BASE_CLAVE = 'autin_fotos_base_url'   # URL del servidor de fotos de la PC (24/7)
AUTIN_TOKEN_CLAVE = 'autin_fotos_token'     # token opcional (?k=) del servidor de fotos
_AUTIN_IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic', '.avif')
_AUTIN_ESTADOS = ('llegada', 'completado', 'salida', 'suspendido', 'otros')
_AUTIN_LABEL = {'llegada': 'Llegada', 'completado': 'Completado', 'salida': 'Salida',
                'suspendido': 'Suspendido', 'otros': 'Otros'}
_AUTIN_ICONO = {'llegada': 'fa-location-dot', 'completado': 'fa-flag-checkered',
                'salida': 'fa-door-open', 'suspendido': 'fa-pause', 'otros': 'fa-images'}
_AUTIN_MAX_FOTOS = 500
_AUTIN_MAX_PROF = 3
_AUTIN_ZIP_MAX = 400 * 1024 * 1024  # tope del ZIP generado en memoria (400 MB)


def _autin_norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()


def _autin_estado(nombre):
    """Clasifica el archivo por el prefijo/palabra de estado en su nombre."""
    base = _autin_norm(os.path.splitext(str(nombre or ''))[0])
    if 'susp' in base or 'deten' in base:
        return 'suspendido'
    if 'arrive' in base or 'arrival' in base or 'llegad' in base or 'inicio' in base or 'entrad' in base:
        return 'llegada'
    if 'complete' in base or 'completad' in base or 'cierre' in base or 'finaliz' in base or 'terminad' in base:
        return 'completado'
    if 'leave' in base or 'leaving' in base or 'salida' in base or 'exit' in base:
        return 'salida'
    return 'otros'


def _autin_dentro(raiz, destino):
    try:
        return os.path.commonpath([raiz, destino]) == raiz
    except Exception:
        return False


def _autin_raiz(pid):
    """Raíz configurada: env > AppConfig(del proyecto del WO) > AppConfig(sesión) > carpeta por defecto."""
    p = (os.environ.get('AUTIN_FOTOS_DIR') or '').strip().strip('"')
    origen = 'env'
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
            origen = 'proyecto'
    if not p:
        cfg = AppConfig.query.filter_by(clave=AUTIN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
            origen = 'global'
    if not p:
        p = os.path.join(BASE_DIR, 'fotos_autin')
        origen = 'defecto'
    return p, origen


def _autin_base_url(pid):
    """URL pública del servidor de fotos (la PC que deja de estar 24/7).
       Vacío = se leen las fotos del disco local (modo actual)."""
    p = (os.environ.get('AUTIN_FOTOS_BASE_URL') or '').strip().strip('"').rstrip('/')
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_BASE_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip().rstrip('/')
    if not p:
        cfg = AppConfig.query.filter_by(clave=AUTIN_BASE_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip().rstrip('/')
    return p


def _autin_token(pid):
    """Token opcional que exige el servidor de fotos (?k=...)."""
    p = (os.environ.get('AUTIN_FOTOS_TOKEN') or '').strip()
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_TOKEN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
    if not p:
        cfg = AppConfig.query.filter_by(clave=AUTIN_TOKEN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
    return p


def _autin_url(base, ruta, token='', qs=''):
    """Arma una URL del servidor de fotos: <base>/<ruta>[?k=...&qs]"""
    u = str(base or '').rstrip('/') + '/' + str(ruta or '').lstrip('/')
    pares = []
    if token:
        pares.append('k=' + urllib.parse.quote(str(token)))
    if qs:
        pares.append(str(qs))
    return u + (('?' + '&'.join(pares)) if pares else '')


def _autin_ping(base, token='', timeout=2.0):
    """¿Responde el servidor de fotos? (si la PC está apagada, False)."""
    try:
        req = urllib.request.Request(_autin_url(base, 'healthz', token),
                                     headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, 'status', 200) < 300
    except Exception:
        return False


def _autin_remota(base, token, wo, timeout=6.0):
    """Lee el listado de fotos del WO desde el servidor de la PC.
       Devuelve el dict del servidor o None si no responde."""
    try:
        qs = 'wo=' + urllib.parse.quote(str(wo))
        req = urllib.request.Request(_autin_url(base, 'api/fotos', token, qs),
                                     headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


_AUTIN_HREF_RE = re.compile(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
_AUTIN_PREFIJO_CACHE = {}   # (base, raiz) -> (ts, prefijo)


def _autin_enc(ruta):
    """Codifica cada segmento de una ruta relativa conservando los '/'."""
    return '/'.join(urllib.parse.quote(str(p)) for p in str(ruta or '').split('/'))


def _autin_http_get(url, timeout=8.0):
    """GET en texto plano. None si no responde o el estado no es 2xx."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= getattr(resp, 'status', 200) < 300):
                return None
            return resp.read().decode('utf-8', 'replace')
    except Exception:
        return None


def _autin_listado(url, timeout=8.0):
    """Lee un listado HTML de directorios (python -m http.server, nginx).
       Devuelve [(nombre, es_dir)] o None si la página no es un listado."""
    doc = _autin_http_get(url, timeout)
    if doc is None:
        return None
    baja = doc.lower()
    if 'directory listing for' not in baja and 'index of ' not in baja and \
       'parent directory' not in baja and '../' not in doc:
        return None
    entradas = []
    for href, _texto in _AUTIN_HREF_RE.findall(doc):
        h = href.strip()
        if not h or h.startswith(('#', '?', 'http://', 'https://')):
            continue
        nombre = urllib.parse.unquote(h).lstrip('/')
        if nombre.startswith('..') or '/' in nombre.rstrip('/'):
            continue
        nombre = nombre.rstrip('/')
        if nombre:
            entradas.append((nombre, h.endswith('/')))
    return entradas


def _autin_modo(base, token='', timeout=8.0):
    """Cómo entrega las fotos la URL guardada:
       'api' = servidor_api (con /healthz) · 'estatico' = python -m http.server · '' = sin servidor."""
    if not base:
        return ''
    if _autin_ping(base, token, timeout=2.5):
        return 'api'
    raices = _autin_listado(_autin_url(base, '', token), timeout)
    if raices and any(d for _n, d in raices):
        return 'estatico'
    return ''


def _autin_prefijo_estatico(base, raiz, token='', timeout=8.0):
    """Carpeta dentro del servidor que contiene la raíz de fotos ('' = ya es la raíz del servidor)."""
    clave = (base, str(raiz or ''))
    hit = _AUTIN_PREFIJO_CACHE.get(clave)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    valor = None
    nombre = os.path.basename(str(raiz or '').rstrip('\\/'))
    if nombre and _autin_listado(_autin_url(base, _autin_enc(nombre), token), timeout) is not None:
        valor = nombre
    elif _autin_listado(_autin_url(base, '', token), timeout) is not None:
        valor = ''
    if valor is not None:
        _AUTIN_PREFIJO_CACHE[clave] = (time.time(), valor)
    return valor


def _autin_carpeta_estatica(base, prefijo, wo, token='', timeout=8.0):
    """Carpeta del WO dentro del servidor (misma lógica que _autin_carpeta pero sobre el listado)."""
    wo_l = _autin_norm(wo)
    if not wo_l:
        return None
    ruta = _autin_enc(prefijo) + '/' if prefijo else ''
    entradas = _autin_listado(_autin_url(base, ruta, token), timeout)
    if entradas is None:
        return None
    carpetas = [n for n, d in entradas if d]
    for nivel in (0, 1, 2):
        for n in carpetas:
            nn = _autin_norm(n)
            if (nivel == 0 and nn == wo_l) or (nivel == 1 and nn.startswith(wo_l)) or \
               (nivel == 2 and wo_l in nn):
                return n
    return None


def _autin_listar_estatico(base, carpeta_rel, token='', timeout=8.0):
    """Imágenes del WO recorriendo los listados HTML (equivalente remoto de _autin_listar)."""
    encontrados = []
    pendientes = [(_autin_enc(carpeta_rel), '', 0)]
    while pendientes and len(encontrados) < _AUTIN_MAX_FOTOS:
        u, rel, prof = pendientes.pop(0)
        entradas = _autin_listado(_autin_url(base, u + '/', token), timeout)
        if entradas is None:
            continue
        for nombre, es_dir in entradas:
            if len(encontrados) >= _AUTIN_MAX_FOTOS:
                break
            if es_dir:
                if prof < _AUTIN_MAX_PROF:
                    pendientes.append((u + '/' + _autin_enc(nombre), rel + nombre + '/', prof + 1))
                continue
            if os.path.splitext(nombre)[1].lower() in _AUTIN_IMG_EXT:
                encontrados.append(rel + nombre)
    encontrados.sort(key=lambda s: s.lower())
    return encontrados


def _autin_remota_estatica(base, raiz, wo, token='', timeout=8.0):
    """Fotos del WO leídas de un servidor de archivos estático.
       Devuelve {'estado': 'ok'|'sin_carpeta'|'sin_servidor', ...}"""
    prefijo = _autin_prefijo_estatico(base, raiz, token, timeout)
    if prefijo is None:
        return {'estado': 'sin_servidor'}
    carpeta = _autin_carpeta_estatica(base, prefijo, wo, token, timeout)
    if not carpeta:
        return {'estado': 'sin_carpeta'}
    carpeta_rel = (prefijo + '/' + carpeta) if prefijo else carpeta
    return {'estado': 'ok', 'carpeta': carpeta, 'carpeta_rel': carpeta_rel,
            'rels': _autin_listar_estatico(base, carpeta_rel, token, timeout)}


def _autin_get_bytes(url, timeout=45.0):
    """Descarga binaria de un archivo del servidor remoto. None si no está."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= getattr(resp, 'status', 200) < 300):
                return None
            return resp.read()
    except Exception:
        return None


def _autin_proyecto_del_wo(wo):
    for nombre in ('FLM - ENTEL', 'FLM', 'PEXT'):
        proy = Proyecto.query.filter_by(nombre=nombre).first()
        if not proy:
            continue
        if NucleusData.query.filter_by(proyecto_id=proy.id, key_value=wo).first():
            return proy.id
    return None


def _autin_carpeta(raiz, wo):
    """Carpeta del WO dentro de la raíz (nombre exacto, que empiece por el WO o que lo contenga)."""
    wo_l = _autin_norm(wo)
    if not wo_l or not os.path.isdir(raiz):
        return None
    try:
        nombres = sorted(os.listdir(raiz))
    except OSError:
        return None
    carpetas = [n for n in nombres if os.path.isdir(os.path.join(raiz, n))]
    for nivel in (0, 1, 2):  # exacto → prefijo → contiene
        for n in carpetas:
            nn = _autin_norm(n)
            if (nivel == 0 and nn == wo_l) or (nivel == 1 and nn.startswith(wo_l)) or \
               (nivel == 2 and wo_l in nn):
                return os.path.realpath(os.path.join(raiz, n))
    return None


def _autin_listar(carpeta):
    """Devuelve los archivos de imagen de la carpeta del WO (con subcarpetas, profundidad limitada)."""
    raiz_r = os.path.realpath(carpeta)
    encontrados = []
    pendientes = [(raiz_r, 0)]
    while pendientes and len(encontrados) < _AUTIN_MAX_FOTOS:
        actual, prof = pendientes.pop(0)
        try:
            entradas = sorted(os.listdir(actual))
        except OSError:
            continue
        for nombre in entradas:
            if len(encontrados) >= _AUTIN_MAX_FOTOS:
                break
            full = os.path.join(actual, nombre)
            try:
                es_dir = os.path.isdir(full)
            except OSError:
                continue
            if es_dir:
                if prof < _AUTIN_MAX_PROF:
                    pendientes.append((full, prof + 1))
                continue
            if os.path.splitext(nombre)[1].lower() in _AUTIN_IMG_EXT:
                encontrados.append(os.path.relpath(full, raiz_r).replace(os.sep, '/'))
    encontrados.sort(key=lambda s: s.lower())
    return encontrados


@bp.route('/api/autin/fotos', methods=['GET'])
@login_required
def api_autin_fotos():
    """Agrupa las fotos del WO por estado (llegada/completado/salida/suspendido)."""
    wo = (request.args.get('wo') or request.args.get('key') or '').strip()
    user_id, user_rol, pid_sesion = get_session_info()
    pid = _autin_proyecto_del_wo(wo) or pid_sesion
    if not wo:
        return jsonify({'success': False, 'error': 'Falta el número de WO'}), 400
    raiz, origen = _autin_raiz(pid)
    base_url = _autin_base_url(pid)
    token = _autin_token(pid)
    es_admin = user_rol in ('zeno', 'suport')
    base = {'success': True, 'wo': wo, 'raiz': raiz if es_admin else '', 'origen': origen if es_admin else '',
            'raiz_existe': os.path.isdir(raiz), 'carpeta': None, 'total': 0,
            'base_url': base_url if user_rol == 'zeno' else '',
            'modo': 'local' if not base_url else '', 'fotos_base': '', 'fotos_qs': '',
            'zip_url': '',
            'grupos': {e: [] for e in _AUTIN_ESTADOS}}

    # ── Modo servidor: las fotos viven en la PC 24/7, se piden a su URL ──────
    # (la 'raiz' local se conserva igual: es el respaldo si se vacía la URL)
    if base_url:
        qs = ('?k=' + urllib.parse.quote(token)) if token else ''
        modo = _autin_modo(base_url, token)
        base['modo'] = modo

        if modo == 'api':  # servidor_api (/healthz + /api/fotos + /zip)
            base['fotos_base'] = base_url + '/f/' + urllib.parse.quote(wo)
            base['fotos_qs'] = qs
            base['zip_url'] = _autin_url(base_url, 'zip', token, 'wo=' + urllib.parse.quote(wo))
            info = _autin_remota(base_url, token, wo)
            if info is None:
                base['modo'] = ''
                base['raiz_existe'] = False
                base['sin_conexion'] = True
                base['mensaje'] = 'Servidor de fotos no disponible (la PC está apagada o sin internet).'
                return jsonify(base)
            base['raiz_existe'] = True
            base['sin_conexion'] = False
            base['carpeta'] = info.get('carpeta') or None
            base['grupos'] = info.get('grupos') or {e: [] for e in _AUTIN_ESTADOS}
            base['total'] = info.get('total') or sum(len(v) for v in base['grupos'].values())
            base['mensaje'] = info.get('mensaje') or ''
            return jsonify(base)

        if modo == 'estatico':  # python -m http.server (listados de directorio)
            info = _autin_remota_estatica(base_url, raiz, wo, token)
            if info.get('estado') == 'ok':
                base['raiz_existe'] = True
                base['sin_conexion'] = False
                base['carpeta'] = info.get('carpeta')
                base['fotos_base'] = base_url + '/' + _autin_enc(info['carpeta_rel'])
                base['fotos_qs'] = qs
                for rel in info.get('rels') or []:
                    base['grupos'][_autin_estado(rel)].append(rel)
                base['total'] = sum(len(v) for v in base['grupos'].values())
                if not base['total']:
                    base['mensaje'] = 'La carpeta del WO no contiene imágenes.'
                return jsonify(base)
            if info.get('estado') == 'sin_carpeta':
                base['raiz_existe'] = True
                base['sin_conexion'] = False
                base['mensaje'] = 'Sin carpeta de fotos para este WO.'
                return jsonify(base)

        base['modo'] = ''
        base['raiz_existe'] = False
        base['sin_conexion'] = True
        base['mensaje'] = 'Servidor de fotos no disponible (la PC está apagada o sin internet).'
        return jsonify(base)

    if not base['raiz_existe']:
        base['mensaje'] = 'No se encuentra la carpeta de fotos Autin.'
        return jsonify(base)
    carpeta = _autin_carpeta(raiz, wo)
    if not carpeta:
        base['mensaje'] = 'Sin carpeta de fotos para este WO.'
        return jsonify(base)
    base['carpeta'] = os.path.basename(carpeta)
    raiz_r = os.path.realpath(raiz)
    for rel in _autin_listar(carpeta):
        if not _autin_dentro(raiz_r, os.path.realpath(os.path.join(carpeta, rel))):
            continue
        base['grupos'][_autin_estado(rel)].append(rel)
    base['total'] = sum(len(v) for v in base['grupos'].values())
    if not base['total']:
        base['mensaje'] = 'La carpeta del WO no contiene imágenes.'
    return jsonify(base)


@bp.route('/api/autin/foto', methods=['GET'])
@login_required
def api_autin_foto():
    """Sirve una foto del WO validando que quede dentro de la raíz configurada."""
    wo = (request.args.get('wo') or '').strip()
    rel = (request.args.get('f') or request.args.get('file') or '').strip()
    _, _, pid_sesion = get_session_info()
    pid = _autin_proyecto_del_wo(wo) or pid_sesion
    if not wo or not rel:
        abort(400)
    raiz, _ = _autin_raiz(pid)
    raiz_r = os.path.realpath(raiz)
    if not os.path.isdir(raiz_r):
        abort(404)
    carpeta = _autin_carpeta(raiz_r, wo) or raiz_r
    candidatos = [os.path.join(carpeta, rel), os.path.join(raiz_r, rel)]
    for cand in candidatos:
        full = os.path.realpath(cand)
        if not _autin_dentro(raiz_r, full):
            continue
        if os.path.isfile(full) and os.path.splitext(full)[1].lower() in _AUTIN_IMG_EXT:
            resp = send_file(full, conditional=True)
            resp.headers['Cache-Control'] = 'private, max-age=3600'
            return resp
    abort(404)


@bp.route('/api/autin/zip', methods=['GET'])
@login_required
def api_autin_zip():
    """ZIP con todas las fotos del WO (misma validación de raíz que /api/autin/foto)."""
    wo = (request.args.get('wo') or '').strip()
    if not wo:
        return jsonify({'error': 'Falta el número de WO'}), 400
    _, _, pid_sesion = get_session_info()
    pid = _autin_proyecto_del_wo(wo) or pid_sesion
    base_url = _autin_base_url(pid)
    if base_url:
        token = _autin_token(pid)
        modo = _autin_modo(base_url, token)
        if modo == 'api':
            # Las fotos están en la PC remota: el ZIP lo genera su servidor.
            return jsonify({'error': 'Las fotos están en el servidor remoto.',
                            'zip_url': _autin_url(base_url, 'zip', token,
                                                  'wo=' + urllib.parse.quote(wo))}), 409
        if modo != 'estatico':
            return jsonify({'error': 'Servidor de fotos no disponible.'}), 503
        # Servidor de archivos estático (sin /zip): Render baja las fotos y arma el ZIP.
        raiz, _ = _autin_raiz(pid)
        info = _autin_remota_estatica(base_url, raiz, wo, token)
        if info.get('estado') != 'ok':
            return jsonify({'error': 'No se encontraron las fotos de este WO en el servidor.'}), 404
        qs = ('?k=' + urllib.parse.quote(token)) if token else ''
        fotos_base = base_url + '/' + _autin_enc(info['carpeta_rel'])
        buf = io.BytesIO()
        total = 0
        count = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            for rel in info.get('rels') or []:
                data = _autin_get_bytes(fotos_base + '/' + _autin_enc(rel) + qs)
                if data is None:
                    continue
                total += len(data)
                if total > _AUTIN_ZIP_MAX:
                    return jsonify({'error': 'Las fotos superan el límite de descarga (400 MB).'}), 413
                zf.writestr(rel, data)
                count += 1
        if not count:
            return jsonify({'error': 'La carpeta del WO no contiene imágenes.'}), 404
        buf.seek(0)
        nombre = secure_filename(str(wo)) or 'wo'
        return send_file(buf, mimetype='application/zip', as_attachment=True,
                         download_name='autin_%s.zip' % nombre)
    raiz, _ = _autin_raiz(pid)
    if not os.path.isdir(raiz):
        return jsonify({'error': 'No se encuentra la carpeta de fotos Autin.'}), 404
    carpeta = _autin_carpeta(raiz, wo)
    if not carpeta:
        return jsonify({'error': 'Sin carpeta de fotos para este WO.'}), 404
    raiz_r = os.path.realpath(raiz)
    buf = io.BytesIO()
    total = 0
    count = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
        for rel in _autin_listar(carpeta):
            full = os.path.realpath(os.path.join(carpeta, rel))
            if not _autin_dentro(raiz_r, full) or not os.path.isfile(full):
                continue
            try:
                total += os.path.getsize(full)
                if total > _AUTIN_ZIP_MAX:
                    return jsonify({'error': 'Las fotos superan el límite de descarga (400 MB).'}), 413
                zf.write(full, rel)
                count += 1
            except OSError:
                continue
    if not count:
        return jsonify({'error': 'La carpeta del WO no contiene imágenes.'}), 404
    buf.seek(0)
    nombre = secure_filename(str(wo)) or 'wo'
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='autin_%s.zip' % nombre)


@bp.route('/api/autin/config', methods=['GET', 'POST'])
@login_required
def api_autin_config():
    """Consulta/guarda la raíz de fotos AUTIN (ruta: zeno/suport · URL del servidor: solo zeno).
       El guardado se hace sobre el proyecto del WO (todo el módulo), no por sesión."""
    user_id, user_rol, pid_sesion = get_session_info()
    es_admin = user_rol in ('zeno', 'suport')

    if request.method == 'POST':
        if not es_admin:
            return jsonify({'success': False, 'error': 'Sin permisos'}), 403
        form = request.form
        js = request.get_json(silent=True) or {}

        def _campo(k):
            if k in form:
                return form.get(k, '')
            if k in js:
                return js.get(k) or ''
            return None   # no se envió: no se modifica

        ruta = _campo('ruta')
        base_enviada = _campo('base_url')
        wo = (_campo('wo') or '').strip()

        if base_enviada is not None and user_rol != 'zeno':
            return jsonify({'success': False,
                            'error': 'La URL del servidor de fotos solo puede cambiarla zeno.'}), 403

        base_url = None
        if base_enviada is not None:
            base_url = str(base_enviada).strip().rstrip('/')
            if base_url and not re.match(r'^https?://', base_url):
                return jsonify({'success': False,
                                'error': 'La URL del servidor debe empezar con http:// o https://'}), 400
        if ruta is None and base_url is None:
            return jsonify({'success': False, 'error': 'Nada que guardar.'}), 400

        pid = _autin_proyecto_del_wo(wo) or pid_sesion
        if not pid:
            return jsonify({'success': False, 'error': 'Sin proyecto activo'}), 400

        if ruta is not None:
            cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_CLAVE).first()
            if cfg:
                cfg.valor = str(ruta).strip()
            else:
                db.session.add(AppConfig(proyecto_id=pid, clave=AUTIN_CLAVE, valor=str(ruta).strip()))
        if base_enviada is not None:
            cfgb = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_BASE_CLAVE).first()
            if cfgb:
                cfgb.valor = base_url
            else:
                db.session.add(AppConfig(proyecto_id=pid, clave=AUTIN_BASE_CLAVE, valor=base_url))
        db.session.commit()

    pid = pid_sesion
    raiz, origen = _autin_raiz(pid)
    base_url = _autin_base_url(pid)
    return jsonify({'success': True, 'raiz': raiz if es_admin else '', 'origen': origen if es_admin else '',
                    'base_url': base_url if user_rol == 'zeno' else '',
                    'existe': os.path.isdir(raiz) or bool(base_url), 'editable': es_admin})
