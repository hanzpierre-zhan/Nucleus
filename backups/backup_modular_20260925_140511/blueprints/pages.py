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


bp = Blueprint('pages', __name__)



@bp.route('/')
@login_required
def index():
    user_id, user_rol, pid = get_session_info()
    is_admin = user_rol == 'zeno'
    is_privileged = user_rol in ['zeno', 'suport']

    if not pid:
        # Emergency fallback or find first allowed
        if is_privileged:
            p = Proyecto.query.first()
        else:
            acc = AccesoProyecto.query.filter_by(usuario_id=user_id).first()
            p = db.session.get(Proyecto, acc.proyecto_id) if acc else None
            
        if p:
            session['current_proyecto_id'] = p.id
            session['current_proyecto_nombre'] = p.nombre
            pid = p.id
        else:
            session.clear()
            return render_template('login.html', error="No tiene proyectos asignados. Contacte al administrador.")

    # Verify access to current project
    res_obj = {}
    if not is_privileged:
        acc = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=pid).first()
        if not acc:
            # Dataper/Material: permitir si el usuario tiene FLM o PEXT asignado.
            # Site Name: permitir solo si el usuario tiene FLM asignado.
            proy_check = db.session.get(Proyecto, pid)
            if proy_check and proy_check.nombre in ('Dataper', 'Material'):
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'PEXT'):
                        allowed = True
                        break
                if not allowed:
                    session.clear()
                    return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
            elif proy_check and proy_check.nombre == 'Site Name':
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    session.clear()
                    return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
            elif proy_check and proy_check.nombre == 'Generadores':
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    session.clear()
                    return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
            elif proy_check and proy_check.nombre == 'Combustible':
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    session.clear()
                    return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
            elif proy_check and proy_check.nombre == 'Cotizaciones':
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'PEXT'):
                        allowed = True
                        break
                if not allowed:
                    session.clear()
                    return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
            else:
                session.clear()
                return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
        try:
            res_obj = json.loads(acc.restricciones or '{}')
        except:
            res_obj = {}

    # Load all distinct keys reliably from AppConfig Master Schema
    schema_config = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
    columns_set = set(json.loads(schema_config.valor)) if schema_config else set()
    
    manual_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    manual_cols_data = json.loads(manual_cfg.valor) if manual_cfg else []
    for mc in manual_cols_data:
        columns_set.add(mc['nombre'])

    # Generadores: el campo TECNICO ASIGNADO se llena dinámicamente con los técnicos
    # activos de Dataper con PROYECTO=FLM/PEXT/Claro/Integratel (catálogo declarado por el admin).
    # Combustible: QR ASIGNADO lista los QR declarados en Generadores, TIPO se
    # autocompleta desde el mapa generador->TIPO, TECNICO ASIGNADO lista los técnicos.
    proy_actual = db.session.get(Proyecto, pid)
    proy_actual_nombre = proy_actual.nombre.strip() if proy_actual and proy_actual.nombre else ''
    if proy_actual_nombre in ('Generadores', 'Combustible'):
        dataper_proy = Proyecto.query.filter_by(nombre='Dataper').first()
        tecnicos_set = set()
        if dataper_proy:
            for r in NucleusData.query.filter_by(proyecto_id=dataper_proy.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                est = str(d.get('ESTADO', '')).strip().upper()
                if est and est != 'ACTIVO':
                    continue
                pr = str(d.get('PROYECTO', '')).strip()
                if pr and pr.upper() not in ('FLM', 'PEXT', 'CLARO', 'INTEGRATEL'):
                    continue
                t = str(d.get('TECNICO', '')).strip()
                if t:
                    tecnicos_set.add(t)
        tecnicos_list = sorted(tecnicos_set)
        for mc in manual_cols_data:
            if mc.get('nombre') == 'TECNICO ASIGNADO':
                mc['opciones'] = tecnicos_list

    gen_tipo_map = {}
    gen_tecnico_map = {}
    gen_zona_map = {}
    wo_list = []
    if proy_actual_nombre == 'Combustible':
        gen_proy = Proyecto.query.filter_by(nombre='Generadores').first()
        series_list = []
        if gen_proy:
            for r in NucleusData.query.filter_by(proyecto_id=gen_proy.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                serie = str(d.get('QR ASIGNADO', '')).strip()
                if not serie:
                    continue
                series_list.append(serie)
                gen_tipo_map[serie] = str(d.get('TIPO', '')).strip()
                gen_tecnico_map[serie] = str(d.get('TECNICO ASIGNADO', '')).strip()
                gen_zona_map[serie] = str(d.get('ZONA', '')).strip()
        series_list = sorted(set(series_list))
        for mc in manual_cols_data:
            if mc.get('nombre') == 'QR ASIGNADO':
                mc['opciones'] = series_list

        # WOs del proyecto FLM para el buscador del campo WO NUMBER
        wo_list = _flm_wo_list()
        for mc in manual_cols_data:
            if mc.get('nombre') == 'WO NUMBER':
                mc['opciones'] = wo_list
    
    # Add KPI columns to the set so frontend can see them
    kpi_configs = KpiConfig.query.filter_by(proyecto_id=pid).all()
    for k in kpi_configs:
        if k.tipo == 'DILACION':
            columns_set.add(f"KPI_{k.nombre}")
    
    # Ocultar columnas internas (prefijo _) y redundantes de la vista
    columns_set = {c for c in columns_set if not c.startswith('_') and c != 'WO Number'}
    # FLM/PEXT: EDITADO POR se reemplaza por GESTOR (quien presiona Guardar, el admin no cuenta).
    if proy_actual_nombre in ('FLM', 'PEXT'):
        columns_set.discard('EDITADO POR')
        columns_set.add('GESTOR')
    # Columna obsoleta que no aporta información (FLM/PEXT).
    for _hc in list(columns_set):
        if 'HORA DE CR' in _hc.upper():
            columns_set.discard(_hc)
    
    # Load and Filter data
    rows = NucleusData.query.filter_by(proyecto_id=pid).all()
    raw_data = []
    for r in rows:
        d = json.loads(r.data_json)
        d['_key'] = r.key_value
        # Visible GESTOR desde EDITADO POR/_ultimo_usuario_manual (FLM/PEXT)
        if proy_actual_nombre in ('FLM', 'PEXT') and not d.get('GESTOR'):
            d['GESTOR'] = d.get('EDITADO POR') or d.get('_ultimo_usuario_manual') or ''
        raw_data.append(d)

    # Dataper y Material: solo mostrar registros cuyo campo PROYECTO sea FLM/PEXT/Claro/Integratel
    # según los proyectos asignados al usuario (si tiene varios, muestra todos). Comparación case-insensitive.
    if proy_actual_nombre in ('Dataper', 'Material'):
        _wo_proys = {'FLM', 'PEXT', 'Claro', 'Integratel'}
        _wo_upper = {p.upper() for p in _wo_proys}
        if is_privileged:
            allowed_proy = set(_wo_proys)
        else:
            accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
            allowed_proy = set()
            for a in accs:
                ap = db.session.get(Proyecto, a.proyecto_id)
                if ap and ap.nombre in _wo_proys:
                    allowed_proy.add(ap.nombre)
        _allowed_upper = {p.upper() for p in allowed_proy}
        raw_data = [d for d in raw_data if str(d.get('PROYECTO', '')).strip().upper() in _allowed_upper]

    # Cruce dinámico: Site Name → FLM. Se agregan a cada fila de FLM las columnas
    # DIRECCION, LATITUD, LONGITUD tomadas del proyecto "Site Name" cruzando por
    # la columna "Nombre de Site" ↔ "NOMBRE DE SITE", solo registros ACTIVOS.
    if proy_actual_nombre == 'FLM':
        site_proy = Proyecto.query.filter_by(nombre='Site Name').first()
        if site_proy:
            site_map = {}
            for sr in NucleusData.query.filter_by(proyecto_id=site_proy.id).all():
                sd = json.loads(sr.data_json)
                if str(sd.get('ESTADO', '')).strip().upper() != 'ACTIVO':
                    continue
                nombre_site = str(sd.get('NOMBRE DE SITE', '')).strip()
                if not nombre_site:
                    continue
                site_map[nombre_site] = {
                    'DIRECCION': sd.get('DIRECCION', ''),
                    'LATITUD': sd.get('LATITUD', ''),
                    'LONGITUD': sd.get('LONGITUD', ''),
                }
            for d in raw_data:
                clave = str(d.get('Nombre de Site', '')).strip()
                info = site_map.get(clave)
                if info:
                    d['DIRECCION'] = info['DIRECCION']
                    d['LATITUD'] = info['LATITUD']
                    d['LONGITUD'] = info['LONGITUD']
            columns_set |= {'DIRECCION', 'LATITUD', 'LONGITUD'}

    data = apply_data_restrictions(raw_data, res_obj)

    # Combustible: saldo disponible por generador (INGRESOS - GASTOS acumulados)
    # y columna SALDO DISPONIBLE para saber cuántos galones quedan por generador.
    gen_saldo_map = {}
    if proy_actual_nombre == 'Combustible':
        try:
            def _parse_gal(n):
                try:
                    return float(str(n or '').replace(',', '.').strip())
                except (ValueError, TypeError):
                    return 0.0
            ordered = sorted(data, key=lambda d: (_combustible_fecha_ord(d.get('FECHA', '')), str(d.get('_key', '') or '')))
            balance = {}
            for d in ordered:
                gen = str(d.get('QR ASIGNADO', '')).strip()
                mov = str(d.get('MOVIMIENTO', '')).strip().upper()
                g = _parse_gal(d.get('GALONES'))
                prev = balance.get(gen, 0.0)
                bal = prev + g if mov != 'GASTO' else prev - g
                balance[gen] = bal
                d['SALDO ANTES'] = round(prev, 2)
                d['SALDO DISPONIBLE'] = round(bal, 2)
            columns_set.add('SALDO DISPONIBLE')
            gen_saldo_map = balance
        except Exception:
            pass

    data, kpi_meta = inject_kpis(pid, data)

    config_key = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
    pk = config_key.valor if config_key else 'NO_DEF'
    
    # Keys con MÁS DE UN cambio de estado registrado (por importación o manual).
    # Cada transición de estado genera una fila en historial_cambios; el filtro
    # solo muestra los WO con más de una transición registrada (>= 2).
    WO_STATE_COL_CH = 'Estado de la tarea (WO State)'
    hist_counts = db.session.query(
        HistorialCambios.key_value,
        db.func.count(HistorialCambios.id)
    ).filter(
        HistorialCambios.proyecto_id == pid,
        HistorialCambios.campo_modificado == WO_STATE_COL_CH
    ).group_by(HistorialCambios.key_value).all()
    changed_keys_set = set(k for k, cnt in hist_counts if cnt > 1)
    changed_keys = sorted(changed_keys_set)
    
    cols = sorted(list(columns_set))
    if '_key' in cols: cols.remove('_key')
    cols.insert(0, '_key')
    # N° ORDEN siempre entre el check y N° COTIZACION (primero visible)
    try:
        if 'N° ORDEN' in cols:
            cols.remove('N° ORDEN')
            if '_key' in cols:
                cols.remove('_key')
                cols.insert(0, '_key')
                cols.insert(0, 'N° ORDEN')
            else:
                cols.insert(0, 'N° ORDEN')
    except Exception:
        pass
    # Si es Cotizaciones o Combustible y no hay layout guardado, forzar orden N° ORDEN primero
    _proj_nombre_for_layout = proy_actual_nombre.lower()
    if _proj_nombre_for_layout in ('cotizaciones', 'combustible') and 'N° ORDEN' in cols:
        # Asegurar que el layout guardado refleje este orden para futuras cargas
        try:
            _layout_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
            if _layout_cfg and _layout_cfg.valor:
                _layout = json.loads(_layout_cfg.valor)
                # Reordenar para que N° ORDEN esté primero
                _order = {c['field']: i for i, c in enumerate(_layout)}
                if 'N° ORDEN' in _order and '_key' in _order:
                    # Si N° ORDEN está después de _key, moverlo antes
                    if _order['N° ORDEN'] > _order['_key']:
                        # Extraer y reinsertar
                        _item_ord = next((x for x in _layout if x['field'] == 'N° ORDEN'), None)
                        _item_key = next((x for x in _layout if x['field'] == '_key'), None)
                        if _item_ord and _item_key:
                            _layout = [x for x in _layout if x['field'] not in ('N° ORDEN', '_key')]
                            _layout.insert(0, _item_ord)
                            _layout.insert(1, _item_key)
                            _layout_cfg.valor = json.dumps(_layout, ensure_ascii=False)
                            db.session.commit()
                elif 'N° ORDEN' not in _order:
                    _layout.insert(0, {'field': 'N° ORDEN', 'visible': True})
                    _layout_cfg.valor = json.dumps(_layout, ensure_ascii=False)
                    db.session.commit()
                # Asegurar que _key esté justo después de N° ORDEN (posición 1)
                _order2 = {c['field']: i for i, c in enumerate(json.loads(_layout_cfg.valor))}
                if 'N° ORDEN' in _order2 and '_key' in _order2 and _order2['_key'] != 1:
                    _layout = json.loads(_layout_cfg.valor)
                    _item_key = next((x for x in _layout if x['field'] == '_key'), None)
                    if _item_key:
                        _layout = [x for x in _layout if x['field'] != '_key']
                        _layout.insert(1, _item_key)
                        _layout_cfg.valor = json.dumps(_layout, ensure_ascii=False)
                        db.session.commit()
                elif 'N° ORDEN' in _order2 and '_key' not in _order2:
                    _layout = json.loads(_layout_cfg.valor)
                    _layout.insert(1, {'field': '_key', 'visible': True})
                    _layout_cfg.valor = json.dumps(_layout, ensure_ascii=False)
                    db.session.commit()
            # Si no hay layout, crearlo con N° ORDEN primero
            _layout_cfg2 = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
            if not _layout_cfg2 or not _layout_cfg2.valor or _layout_cfg2.valor.strip() in ('', '[]'):
                _new_layout = [{'field': c, 'visible': True} for c in cols]
                if _layout_cfg2:
                    _layout_cfg2.valor = json.dumps(_new_layout, ensure_ascii=False)
                else:
                    db.session.add(AppConfig(proyecto_id=pid, clave='column_layout', valor=json.dumps(_new_layout, ensure_ascii=False)))
                db.session.commit()
        except Exception:
            pass

    # FIX: N antes de N° COTIZACION/QR para Cotizaciones/Combustible (corrige layout guardado al revés)
    try:
        _pn_fix = proy_actual_nombre.lower()
        if _pn_fix in ('cotizaciones','combustible'):
            _cfg_fix = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
            if _cfg_fix and _cfg_fix.valor:
                _lyt = json.loads(_cfg_fix.valor)
                _fields = [c['field'] for c in _lyt]
                if 'N° ORDEN' in _fields and '_key' in _fields and _fields.index('N° ORDEN') > _fields.index('_key'):
                    _lyt = [c for c in _lyt if c['field'] not in ('N° ORDEN','_key')]
                    _lyt.insert(0, {'field':'N° ORDEN','visible':True})
                    _lyt.insert(1, {'field':'_key','visible':True})
                    _cfg_fix.valor = json.dumps(_lyt, ensure_ascii=False)
                    db.session.commit()
    except: pass
    # Layout de columnas definido por el admin (orden + visibilidad) para todos los usuarios.
    layout_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
    column_layout = json.loads(layout_cfg.valor) if layout_cfg and layout_cfg.valor else []
    
    # List allowed projects for the menu
    proyectos = get_menu_proyectos(user_id, user_rol)
    
    return render_template('index.html', 
                          data=json.dumps(data), 
                          columns=json.dumps(cols), 
                          pk=pk, 
                          manual_cols=json.dumps(manual_cols_data),
                          column_layout=json.dumps(column_layout),
                          kpi_meta=json.dumps(kpi_meta),
                          changed_keys=json.dumps(changed_keys),
                          gen_tipo_map=json.dumps(gen_tipo_map),
                          gen_tecnico_map=json.dumps(gen_tecnico_map),
                          gen_zona_map=json.dumps(gen_zona_map),
                          gen_saldo_map=json.dumps(gen_saldo_map),
                          wo_list=json.dumps(wo_list),
                          proyecto_id=pid,
                          proyectos_list=proyectos)


@bp.route('/dashboard')
@login_required
def dashboard():
    user_id, user_rol, pid = get_session_info()
    is_admin = user_rol == 'zeno'

    # El rol Contrata no accede a dashboards; el Gestor sí (solo lectura)
    if user_rol in ('contrata',):
        return redirect(url_for('pages.index'))

    if not pid:
        return redirect(url_for('pages.index'))

    # Verify access to current project
    res_obj = {}
    is_privileged = user_rol in ['zeno', 'suport']

    if not is_privileged:
        acc = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=pid).first()
        if not acc:
            proy_check = db.session.get(Proyecto, pid)
            if proy_check and proy_check.nombre in ('Dataper', 'Material', 'Site Name', 'Generadores', 'Combustible'):
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'PEXT'):
                        allowed = True
                        break
                if not allowed:
                    session.clear()
                    return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
            else:
                session.clear()
                return render_template('login.html', error="Acceso denegado a este proyecto. Por favor, solicite acceso al administrador.")
        try:
            res_obj = json.loads(acc.restricciones or '{}')
        except:
            res_obj = {}

    schema_config = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
    columns_set = set(json.loads(schema_config.valor)) if schema_config else set()
    
    manual_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    manual_cols_data = json.loads(manual_cfg.valor) if manual_cfg else []
    for mc in manual_cols_data:
        columns_set.add(mc['nombre'])
        
    kpi_configs = KpiConfig.query.filter_by(proyecto_id=pid).all()
    for k in kpi_configs:
        if k.tipo == 'DILACION':
            columns_set.add(f"KPI_{k.nombre}")
    
    # Ocultar columnas internas (prefijo _) y redundantes de la vista
    columns_set = {c for c in columns_set if not c.startswith('_') and c != 'WO Number'}
    # Columna obsoleta que no aporta información (FLM/PEXT).
    for _hc in list(columns_set):
        if 'HORA DE CR' in _hc.upper():
            columns_set.discard(_hc)
    
    rows = NucleusData.query.filter_by(proyecto_id=pid).limit(5000).all()
    raw_data = []
    for r in rows:
        d = json.loads(r.data_json)
        d['_key'] = r.key_value
        raw_data.append(d)

    # Dataper y Material: solo mostrar registros cuyo campo PROYECTO sea FLM o PEXT
    # según los proyectos asignados al usuario (si tiene ambos, muestra ambos).
    proy_actual = db.session.get(Proyecto, pid)
    proy_actual_nombre = proy_actual.nombre.strip() if proy_actual and proy_actual.nombre else ''
    # FLM/PEXT: GESTOR = quien presiona Guardar (el admin no cuenta).
    if proy_actual_nombre in ('FLM', 'PEXT'):
        columns_set.discard('EDITADO POR')
        columns_set.add('GESTOR')
        for d in raw_data:
            if not d.get('GESTOR'):
                d['GESTOR'] = d.get('EDITADO POR') or d.get('_ultimo_usuario_manual') or ''
    if proy_actual_nombre in ('Dataper', 'Material'):
        _wo_proys2 = {'FLM', 'PEXT', 'Claro', 'Integratel'}
        _wo_upper2 = {p.upper() for p in _wo_proys2}
        if is_privileged:
            allowed_proy = set(_wo_proys2)
        else:
            accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
            allowed_proy = set()
            for a in accs:
                ap = db.session.get(Proyecto, a.proyecto_id)
                if ap and ap.nombre in _wo_proys2:
                    allowed_proy.add(ap.nombre)
        _allowed_upper2 = {p.upper() for p in allowed_proy}
        raw_data = [d for d in raw_data if str(d.get('PROYECTO', '')).strip().upper() in _allowed_upper2]
        
    data = apply_data_restrictions(raw_data, res_obj)
        
    data, kpi_meta = inject_kpis(pid, data)

    cols = sorted(list(columns_set))
    
    # List allowed projects for the menu
    proyectos = get_menu_proyectos(user_id, user_rol)

    # Load saved configurations
    dash_config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_charts').first()
    saved_charts = json.loads(dash_config.valor) if dash_config else []
    
    kpi_config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_kpis').first()
    saved_kpis = json.loads(kpi_config.valor) if kpi_config else []
    
    filt_config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_filters').first()
    saved_filters = json.loads(filt_config.valor) if filt_config else []
    
    # Get current project name
    proj = Proyecto.query.get(pid)
    proyecto_nombre = proj.nombre if proj else "Gestión"
    
    return render_template('dashboard.html', 
                          data=json.dumps(data), 
                          columns=json.dumps(cols), 
                          proyectos_list=proyectos,
                          saved_charts=json.dumps(saved_charts),
                          saved_kpis=json.dumps(saved_kpis),
                          saved_filters=json.dumps(saved_filters),
                          proyecto_nombre=proyecto_nombre)


@bp.route('/configuraciones')
@login_required
def configuraciones():
    user_rol = str(session.get('rol') or 'supervisor').strip().lower()
    if user_rol in ('gestor', 'contrata'):
        return redirect(url_for('pages.index'))
    user_id = session.get('user_id')
    if user_rol == 'zeno':
        proyectos = Proyecto.query.all()
    else:
        accesos = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
        pids = [a.proyecto_id for a in accesos]
        proyectos = Proyecto.query.filter(Proyecto.id.in_(pids)).all()
    return render_template('configuraciones.html', proyectos_list=proyectos)


@bp.route('/admin')
@login_required
def admin_panel():
    if session.get('rol') not in ('zeno', 'suport'):
        return redirect(url_for('pages.index'))
    return redirect(url_for('pages.proyectos_page'))


@bp.route('/proyectos')
@login_required
def proyectos_page():
    if session.get('rol') not in ('zeno', 'suport'):
        return redirect(url_for('pages.index'))
    proy = Proyecto.query.order_by(Proyecto.id).all()
    return render_template('proyectos.html', proyectos=proy, proyectos_list=proy)


@bp.route('/usuarios')
@login_required
def usuarios_page():
    if session.get('rol') not in ('zeno', 'suport'):
        return redirect(url_for('pages.index'))
    proy = Proyecto.query.order_by(Proyecto.id).all()
    user = Usuario.query.all()
    accesos = {}
    for a in AccesoProyecto.query.all():
        accesos.setdefault(a.usuario_id, []).append(a.proyecto_id)
    return render_template('usuarios.html', proyectos=proy, usuarios=user, proyectos_list=proy, accesos=accesos)


@bp.route('/healthz')
def healthz():
    return 'OK', 200


@bp.route('/mapa-site')
@bp.route('/mapa')
@login_required
def mapa_site():
    """Mapa de sites del maestro SITE (lat/lng) con buscador para resaltar."""
    user_id = session.get('user_id')
    user_rol = session.get('rol')
    # Permiso: admin/demo o cualquier usuario con FLM (como SITE en el menú)
    proy_site = Proyecto.query.filter_by(nombre='SITE').first()
    if not proy_site:
        from flask import abort
        abort(404)
    if user_rol not in ('zeno', 'suport'):
        # Debe tener FLM para ver el mapa de sites
        flm = Proyecto.query.filter_by(nombre='FLM').first()
        has_flm = False
        if flm:
            has_flm = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=flm.id).first() is not None
        if not has_flm:
            has_flm = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=proy_site.id).first() is not None
        if not has_flm:
            from flask import redirect, url_for
            return redirect(url_for('pages.index'))
    # Contar sites con coordenadas válidas (para el hint)
    count_valid = 0
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
        if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0):
            count_valid += 1
    proyectos = get_menu_proyectos(user_id, user_rol)
    return render_template('mapa_site.html', sites_count=count_valid, proyectos_list=proyectos)