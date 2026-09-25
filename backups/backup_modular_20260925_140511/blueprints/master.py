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


bp = Blueprint('master', __name__)



@bp.route('/api/master/filtros', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_master_filtros():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar filtros.'}), 403
    if request.method == 'GET':
        qs = FiltroMaestro.query.filter_by(proyecto_id=pid).all()
        return jsonify([{'id': q.id, 'columna': q.columna, 'valor': q.valor} for q in qs])
    if request.method == 'POST':
        data = request.json
        try:
            nuevo = FiltroMaestro(proyecto_id=pid, columna=data['columna'].strip(), valor=data['valor'].strip())
            db.session.add(nuevo)
            db.session.commit()
            return jsonify({'success': True, 'id': nuevo.id})
        except:
            db.session.rollback()
            return jsonify({'error': 'Duplicated or invalid'}), 400
    if request.method == 'DELETE':
        data = request.json
        if data.get('clear_all'):
            FiltroMaestro.query.filter_by(proyecto_id=pid).delete()
            db.session.commit()
            return jsonify({'success': True})
        
        id = data.get('id')
        if id:
            f = FiltroMaestro.query.filter_by(id=id, proyecto_id=pid).first()
            if f:
                db.session.delete(f)
                db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/master/tablas', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_master_tablas():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar tablas maestras.'}), 403
    if request.method == 'GET':
        qs = TablaMaestra.query.filter_by(proyecto_id=pid).all()
        return jsonify([{'id': q.id, 'columna_criterio': q.columna_criterio, 'valor_criterio': q.valor_criterio, 'nueva_columna': q.nueva_columna, 'nuevo_valor': q.nuevo_valor} for q in qs])
    if request.method == 'POST':
        data = request.json
        nuevo = TablaMaestra(
            proyecto_id=pid,
            columna_criterio=data['columna_criterio'].strip(),
            valor_criterio=data['valor_criterio'].strip(),
            nueva_columna=data['nueva_columna'].strip(),
            nuevo_valor=data['nuevo_valor'].strip(),
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({'success': True, 'id': nuevo.id})
    if request.method == 'DELETE':
        data = request.json
        if data.get('clear_all'):
            TablaMaestra.query.filter_by(proyecto_id=pid).delete()
            db.session.commit()
            return jsonify({'success': True})
            
        id = data.get('id')
        if id:
            f = TablaMaestra.query.filter_by(id=id, proyecto_id=pid).first()
            if f:
                db.session.delete(f)
                db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/master/reglas_manuales', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_master_reglas_manuales():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar reglas manuales.'}), 403
    if request.method == 'GET':
        qs = ReglaEstadoManual.query.filter_by(proyecto_id=pid).all()
        return jsonify([{'id': q.id, 'columna_criterio': q.columna_criterio, 'valor_criterio': q.valor_criterio, 'columna_manual': q.columna_manual, 'nuevo_valor': q.nuevo_valor} for q in qs])
    if request.method == 'POST':
        data = request.json
        nuevo = ReglaEstadoManual(
            proyecto_id=pid,
            columna_criterio=data['columna_criterio'].strip(),
            valor_criterio=data['valor_criterio'].strip(),
            columna_manual=data['columna_manual'].strip(),
            nuevo_valor=data['nuevo_valor'].strip(),
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({'success': True, 'id': nuevo.id})
    if request.method == 'DELETE':
        data = request.json
        if data.get('clear_all'):
            ReglaEstadoManual.query.filter_by(proyecto_id=pid).delete()
            db.session.commit()
            return jsonify({'success': True})
            
        id = data.get('id')
        if id:
            f = ReglaEstadoManual.query.filter_by(id=id, proyecto_id=pid).first()
            if f:
                db.session.delete(f)
                db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/master/reprocess', methods=['POST'])
@login_required
def api_master_reprocess():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para re-procesar datos.'}), 403
    try:
        # 1. Load data update rules (Tablas Maestras & Reglas Manuales)
        tablas = TablaMaestra.query.filter_by(proyecto_id=pid).all()
        reglas = []
        for t in tablas:
            t_cols = [c.strip() for c in t.columna_criterio.split(',')]
            t_vals = [v.strip() for v in t.valor_criterio.split(',')]
            reglas.append({
                'condiciones': list(zip(t_cols, t_vals)),
                'nueva_columna': t.nueva_columna,
                'nuevo_valor': t.nuevo_valor
            })
            
        reglas_manuales = ReglaEstadoManual.query.filter_by(proyecto_id=pid).all()
        for r in reglas_manuales:
            r_cols = [c.strip() for c in r.columna_criterio.split(',')]
            r_vals = [v.strip() for v in r.valor_criterio.split(',')]
            reglas.append({
                'condiciones': list(zip(r_cols, r_vals)),
                'nueva_columna': r.columna_manual,
                'nuevo_valor': r.nuevo_valor
            })

        # 2. Load Filter Rules (Clusters)
        filtros = FiltroMaestro.query.filter_by(proyecto_id=pid).all()
        raw_reglas_filtros = []
        for f in filtros:
            f_cols = [c.strip() for c in f.columna.split(',')]
            f_vals = [v.strip() for v in f.valor.split(',')]
            raw_reglas_filtros.append({'cols': set(f_cols), 'pairs': list(zip(f_cols, f_vals))})
            
        temp_clusters = []
        for r in raw_reglas_filtros:
            assigned = False
            for group in temp_clusters:
                if any(c in group['columns'] for c in r['cols']):
                    group['columns'].update(r['cols'])
                    group['rules'].append(r['pairs'])
                    assigned = True
                    break
            if not assigned:
                temp_clusters.append({'columns': r['cols'], 'rules': [r['pairs']]})
                
        # Consolidar clusters transitivos
        final_clusters = []
        for c in temp_clusters:
            merged = False
            for f in final_clusters:
                if c['columns'] & f['columns']:
                    f['columns'].update(c['columns'])
                    f['rules'].extend(c['rules'])
                    merged = True
                    break
            if not merged:
                final_clusters.append(c)

        # 3. Load Consolidation Config
        cons_cfg_row = AppConfig.query.filter_by(proyecto_id=pid, clave='consolidation_config').first()
        cons_cfg = json.loads(cons_cfg_row.valor) if cons_cfg_row else {}
        consolidate_on_fail = cons_cfg.get('consolidate_on_filter_fail', False)

        # 4. Process Data
        records = NucleusData.query.filter_by(proyecto_id=pid).all()
        updated, consolidated = 0, 0
        new_columns = set()
        
        for record in records:
            row_dict = json.loads(record.data_json)
            data_changed = False
            
            # Apply update rules
            for regla in reglas:
                match = True
                for c, v in regla['condiciones']:
                    if str(row_dict.get(c, '')) != v:
                        match = False; break
                if match:
                    if row_dict.get(regla['nueva_columna']) != regla['nuevo_valor']:
                        row_dict[regla['nueva_columna']] = regla['nuevo_valor']
                        new_columns.add(regla['nueva_columna'])
                        data_changed = True
            
            # Check Consolidation Rules
            move_to_history = False
            
            # Filter-fail-based
            if consolidate_on_fail and final_clusters:
                keep_record = True
                for cluster in final_clusters:
                    match_cluster = False
                    for rule in cluster['rules']:
                        match_rule = True
                        for c, v in rule:
                            val_archivo = str(row_dict.get(c, '')).strip().upper()
                            val_filtro = str(v).strip().upper()
                            if val_archivo != val_filtro:
                                match_rule = False
                                break
                        if match_rule:
                            match_cluster = True
                            break
                    if not match_cluster:
                        keep_record = False
                        break
                
                if not keep_record:
                    move_to_history = True

            if move_to_history:
                new_hist = NucleusHistory(proyecto_id=pid, key_value=record.key_value, data_json=safe_json_dumps(row_dict))
                db.session.add(new_hist)
                db.session.delete(record)
                consolidated += 1
                updated += 1
            elif data_changed:
                record.data_json = safe_json_dumps(row_dict)
                updated += 1
        
        db.session.commit()
        
        # Update schema if new columns were found
        if new_columns:
            config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
            if config_schema:
                schema_cols = set(json.loads(config_schema.valor))
                if not new_columns.issubset(schema_cols):
                    updated_schema = list(schema_cols.union(new_columns))
                    config_schema.valor = safe_json_dumps(updated_schema)
                    db.session.commit()

        return jsonify({'success': True, 'updated': updated, 'consolidated': consolidated})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/master/manual_columns', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_manual_columns():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar columnas manuales.'}), 403
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    cols = json.loads(config.valor) if config else []
    if request.method == 'GET':
        return jsonify(cols)
    if request.method == 'POST':
        data = request.json
        new_col = {
            'nombre': data['nombre'].strip(),
            'tipo': data['tipo'].strip(),
            'opciones': [opt.strip() for opt in data.get('opciones', '').split(',') if opt.strip()]
        }
        for c in cols:
            if c['nombre'].lower() == new_col['nombre'].lower():
                return jsonify({'error': 'Columna ya existe'}), 400
        cols.append(new_col)
        if config:
            config.valor = safe_json_dumps(cols)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='manual_columns', valor=safe_json_dumps(cols)))
        db.session.commit()
        return jsonify({'success': True})
    if request.method == 'DELETE':
        nombre = request.json.get('nombre')
        cols = [c for c in cols if c['nombre'] != nombre]
        if config:
            config.valor = safe_json_dumps(cols)
            db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/columns/layout', methods=['GET', 'POST'])
@login_required
def api_columns_layout():
    """Orden y visibilidad de columnas definidos por el admin; se aplican a todos los usuarios."""
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
    if request.method == 'GET':
        return jsonify(json.loads(config.valor) if config and config.valor else [])
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo el administrador puede configurar las columnas.'}), 403
    data = request.get_json(silent=True) or {}
    columns = data.get('columns') or []
    cleaned = []
    for c in columns:
        if not isinstance(c, dict):
            continue
        field = str(c.get('field', '')).strip()
        if not field or field == '_key' or field.startswith('KPI_'):
            continue
        cleaned.append({'field': field, 'visible': bool(c.get('visible', True))})
    if cleaned:
        if config:
            config.valor = safe_json_dumps(cleaned)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='column_layout', valor=safe_json_dumps(cleaned)))
    else:
        if config:
            db.session.delete(config)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/api/master/dashboard_charts', methods=['GET', 'POST'])
@login_required
def api_dashboard_charts():
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_charts').first()
    
    if request.method == 'GET':
        charts = json.loads(config.valor) if config else []
        return jsonify(charts)
        
    if request.method == 'POST':
        if session.get('rol') in ['demo', 'contrata', 'gestor']:
            return jsonify({'error': 'Rol sin permisos para modificar el dashboard.'}), 403
        charts = request.json # Expecting an array of chart objects
        if config:
            config.valor = safe_json_dumps(charts)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='saved_dashboard_charts', valor=safe_json_dumps(charts)))
        db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/master/dashboard_kpis', methods=['GET', 'POST'])
@login_required
def api_dashboard_kpis():
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_kpis').first()
    
    if request.method == 'GET':
        kpis = json.loads(config.valor) if config else []
        return jsonify(kpis)
        
    if request.method == 'POST':
        if session.get('rol') in ['demo', 'contrata', 'gestor']:
            return jsonify({'error': 'Rol sin permisos para modificar el dashboard.'}), 403
        kpis = request.json
        if config:
            config.valor = safe_json_dumps(kpis)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='saved_dashboard_kpis', valor=safe_json_dumps(kpis)))
        db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/master/all_columns')
@login_required
def api_master_all_columns():
    pid = session.get('current_proyecto_id')
    schema_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
    manual_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    
    cols = set()
    if schema_cfg:
        try: cols.update(json.loads(schema_cfg.valor))
        except: pass
    if manual_cfg:
        try:
            m_list = json.loads(manual_cfg.valor)
            for m in m_list:
                cols.add(m['nombre'])
        except: pass
        
    return jsonify(sorted(list(cols)))


@bp.route('/api/master/dashboard_filters', methods=['GET', 'POST'])
@login_required
def api_dashboard_filters():
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_filters').first()
    
    if request.method == 'GET':
        filters = json.loads(config.valor) if config else []
        return jsonify(filters)
        
    if request.method == 'POST':
        if session.get('rol') in ['demo', 'contrata', 'gestor']:
            return jsonify({'error': 'Rol sin permisos para modificar filtros del dashboard.'}), 403
        filters = request.json
        if config:
            config.valor = safe_json_dumps(filters)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='saved_dashboard_filters', valor=safe_json_dumps(filters)))
        db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/master/template/<tipo>')
@login_required
def api_master_template(tipo):
    output = io.BytesIO()
    if tipo == 'filtros':
        df = pd.DataFrame(columns=['columna', 'valor'])
        filename = "Plantilla_Filtros.xlsx"
    elif tipo == 'tablas':
        df = pd.DataFrame(columns=['columna_criterio', 'valor_criterio', 'nueva_columna', 'nuevo_valor'])
        filename = "Plantilla_Cruces.xlsx"
    else:
        return "Tipo no válido", 400
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantilla')
    
    output.seek(0)
    from flask import send_file
    return send_file(output, download_name=filename, as_attachment=True)


@bp.route('/api/master/bulk_import/<tipo>', methods=['POST'])
@login_required
def api_master_bulk_import(tipo):
    pid = session.get('current_proyecto_id')
    if session.get('rol') in ('demo', 'gestor', 'contrata'):
        return jsonify({'error': 'Sin permisos para realizar importaciones masivas.'}), 403
    if 'file' not in request.files:
        return jsonify({'error': 'No se subió ningún archivo'}), 400
    
    file = request.files['file']
    try:
        df = pd.read_excel(file, dtype=str).fillna('')
        df.columns = [c.strip().lower() for c in df.columns]
        
        added = 0
        if tipo == 'filtros':
            required = ['columna', 'valor']
            if not all(c in df.columns for c in required):
                return jsonify({'error': f'Columnas faltantes. Se requiere: {required}'}), 400
            
            for _, row in df.iterrows():
                try:
                    c, v = row['columna'].strip(), row['valor'].strip()
                    if not c or not v: continue
                    # Check duplicate
                    exists = FiltroMaestro.query.filter_by(proyecto_id=pid, columna=c, valor=v).first()
                    if not exists:
                        nuevo = FiltroMaestro(proyecto_id=pid, columna=c, valor=v)
                        db.session.add(nuevo)
                        added += 1
                except: continue
        
        elif tipo == 'tablas':
            required = ['columna_criterio', 'valor_criterio', 'nueva_columna', 'nuevo_valor']
            if not all(c in df.columns for c in required):
                return jsonify({'error': f'Columnas faltantes. Se requiere: {required}'}), 400
            
            for _, row in df.iterrows():
                try:
                    cc, vc = row['columna_criterio'].strip(), row['valor_criterio'].strip()
                    nc, nv = row['nueva_columna'].strip(), row['nuevo_valor'].strip()
                    if not all([cc, vc, nc, nv]): continue
                    nuevo = TablaMaestra(proyecto_id=pid, columna_criterio=cc, valor_criterio=vc, nueva_columna=nc, nuevo_valor=nv)
                    db.session.add(nuevo)
                    added += 1
                except: continue
        
        db.session.commit()
        return jsonify({'success': True, 'added': added})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/clean', methods=['POST'])
@login_required
def api_clean():
    if session.get('rol') in ['contrata', 'gestor', 'demo']:
        return jsonify({'error': 'No tienes permisos para esta acción.'}), 403
        
    pid = session.get('current_proyecto_id')
    try:
        NucleusData.query.filter_by(proyecto_id=pid).delete()
        AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').delete()
        AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').delete()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500