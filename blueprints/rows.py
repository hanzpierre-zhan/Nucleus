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


bp = Blueprint('rows', __name__)



@bp.route('/api/rows/update', methods=['POST'])
@login_required
def api_rows_update():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para actualizar datos.'}), 403
    # SITE: solo supervisor/admin puede editar
    _proy_chk = db.session.get(Proyecto, pid)
    if _proy_chk and _proy_chk.nombre.strip() == 'SITE' and session.get('rol') not in ('zeno', 'suport', 'supervisor'):
        return jsonify({'error': 'Solo supervisor o admin puede editar sites.'}), 403
    try:
        data = request.json
        key_val = data.get('key')
        field = data.get('field')
        value = data.get('value')
        if not all([key_val, field]): return jsonify({'error': 'Missing data'}), 400
        record = NucleusData.query.filter_by(proyecto_id=pid, key_value=str(key_val)).first()
        if not record: return jsonify({'error': 'Record not found'}), 404
        row_dict = json.loads(record.data_json)

        # PEXT: fila finalizada → solo zeno/suport/supervisor pueden editar
        _proy_upd = db.session.get(Proyecto, pid)
        _proy_upd_nombre = _proy_upd.nombre.strip() if _proy_upd and _proy_upd.nombre else ''
        if (_proy_upd_nombre in ('PEXT', 'FLM', 'FLM - ENTEL')
                and str(row_dict.get('CATEGORY', '')).strip() == 'O&M PEXT'
                and str(row_dict.get('_FINALIZADO', '')).strip() == '1'
                and session.get('rol') not in ('zeno', 'suport', 'supervisor')):
            return jsonify({'error': 'Este WO est\u00e1 finalizado y no puede editarse. Contacta al supervisor o administrador.'}), 403

        
        # N° ORDEN correlativo: no editable una vez asignado
        if field == 'N° ORDEN':
            cur_ord = str(row_dict.get('N° ORDEN', '') or '').strip()
            if cur_ord and str(value).strip() != cur_ord and session.get('rol') not in ('zeno', 'suport'):
                return jsonify({'error': 'El N° de orden es correlativo automático y no se puede editar.'}), 403
        # Combustible: el gestor solo puede completar información pendiente (campos
        # vacíos); los campos ya registrados solo los edita el admin.
        proy_obj = db.session.get(Proyecto, pid)
        proy_nombre = proy_obj.nombre.strip() if proy_obj and proy_obj.nombre else ''
        if proy_nombre == 'Combustible':
            valor_actual = str(row_dict.get(field, '') or '').strip()
            if session.get('rol') not in ('zeno', 'suport') and valor_actual:
                return jsonify({'error': f'El campo {field} ya está registrado. Solo el administrador puede editarlo.'}), 403
            if field == 'GESTOR':
                return jsonify({'error': 'El campo GESTOR no se puede editar. Es quien registró el movimiento.'}), 400
            # WO NUMBER libre: acepta cualquier código (vacío = CM PENDIENTE).
            if field in ('MOVIMIENTO', 'GALONES', 'QR ASIGNADO', 'FECHA'):
                if field == 'FECHA':
                    # Normalizar formato para que el orden cronológico no se rompa
                    value = _combustible_fecha_norm(value)
                old_gen = str(row_dict.get('QR ASIGNADO', '')).strip()
                new_gen = str(value if field == 'QR ASIGNADO' else row_dict.get('QR ASIGNADO', '')).strip()
                new_mov = str(value if field == 'MOVIMIENTO' else row_dict.get('MOVIMIENTO', '')).strip().upper()
                new_gal = _parse_galones(value if field == 'GALONES' else row_dict.get('GALONES'))
                new_fec = _combustible_fecha_norm(value if field == 'FECHA' else row_dict.get('FECHA', ''))
                nuevo = {'key': str(key_val), 'fecha': new_fec, 'mov': new_mov, 'gal': new_gal}
                # Simulación cronológica: el cambio no puede dejar en negativo
                # ni el generador origen (si el QR cambia o el INGRESO se reduce)
                # ni el generador destino.
                gens_chequear = {old_gen, new_gen} - {''}
                for _g in gens_chequear:
                    _filas = [f for f in _combustible_filas_gen(pid, _g)
                              if str(f.get('key')) != str(key_val)]
                    if _g == new_gen and new_gen:
                        _filas.append(dict(nuevo))
                        _filas.sort(key=lambda f: (_combustible_fecha_ord(f['fecha']), str(f.get('key') or '')))
                    _ok, _info = _combustible_chequear(_filas)
                    if not _ok:
                        return jsonify({'error': (
                            'No hay saldo disponible para este cambio. '
                            f"QR {_g}: al {_info.get('fecha', '')} el saldo quedaría en "
                            f"{_info.get('saldo', 0):g} galones. "
                            'Revise el INGRESO correspondiente antes de editar.')}), 400

        # Cotizaciones: GESTOR y la llave (N° COTIZACION) no se editan; una vez
        # GENERADA, solo el admin puede corregir, salvo NUMERO WO cuando está en CM-PENDIENTE.
        if proy_nombre == 'Cotizaciones':
            if field == 'GESTOR':
                valor_gestor = str(row_dict.get('GESTOR', '') or '').strip()
                if valor_gestor and str(value).strip() != valor_gestor and session.get('rol') not in ('zeno', 'suport'):
                    return jsonify({'error': 'El campo GESTOR no se puede editar. Es quien registró la cotización.'}), 400
                elif not valor_gestor:
                    pass
                else:
                    return jsonify({'success': True})
            if field == 'N° COTIZACION':
                if str(value).strip() != str(key_val).strip():
                    return jsonify({'error': 'El N° de cotización es la llave del registro y no se puede editar.'}), 400
                else:
                    return jsonify({'success': True})
            if session.get('rol') not in ('zeno', 'suport') and str(row_dict.get('GENERADA', '') or '') == '1':
                if field == 'NUMERO WO' and not str(row_dict.get('NUMERO WO', '') or '').strip():
                    pass
                else:
                    return jsonify({'error': 'Esta cotización ya fue GENERADA y está bloqueada. Solo el administrador puede editarla.'}), 403
        
        # Guardar en el historial de cambios (solo si el valor realmente cambió)
        valor_anterior = row_dict.get(field, '')
        if str(valor_anterior) != str(value):
            historial = HistorialCambios(
                proyecto_id=pid,
                usuario_id=session.get('user_id'),
                username=session.get('username'),
                key_value=str(key_val),
                campo_modificado=field,
                valor_anterior=str(valor_anterior),
                valor_nuevo=str(value)
            )
            db.session.add(historial)
            if str(field).strip() == 'Estado de la tarea (WO State)':
                row_dict['FECHA CAMBIO ESTADO'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        row_dict[field] = value
        row_dict['_ultimo_usuario_manual'] = session.get('username')
        row_dict['_fecha_ultima_act_manual'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        row_dict['EDITADO POR'] = session.get('username')
        # FLM/PEXT: GESTOR = quien presiona Guardar; el admin no cuenta.
        if proy_nombre in ('FLM', 'FLM - ENTEL', 'PEXT') and session.get('rol') not in ('zeno', 'suport'):
            row_dict['GESTOR'] = session.get('username')
        
        # --- Instant Logic: Re-apply TablaMaestra rules for this row ---
        tablas = TablaMaestra.query.filter_by(proyecto_id=pid).all()
        for t in tablas:
            t_cols = [c.strip() for c in t.columna_criterio.split(',')]
            t_vals = [v.strip() for v in t.valor_criterio.split(',')]
            
            match = True
            for c, v in zip(t_cols, t_vals):
                if str(row_dict.get(c, '')) != v:
                    match = False
                    break
            if match:
                row_dict[t.nueva_columna] = t.nuevo_valor

        # --- Re-apply Reglas de Estado Manual ---
        reglas_manuales = ReglaEstadoManual.query.filter_by(proyecto_id=pid).all()
        for r in reglas_manuales:
            r_cols = [c.strip() for c in r.columna_criterio.split(',')]
            r_vals = [v.strip() for v in r.valor_criterio.split(',')]
            
            match = True
            for c, v in zip(r_cols, r_vals):
                if str(row_dict.get(c, '')) != v:
                    match = False
                    break
            if match:
                row_dict[r.columna_manual] = r.nuevo_valor

        record.data_json = safe_json_dumps(row_dict)
        # FLM <-> FLM - ENTEL: propaga el campo editado al CM espejo del otro proyecto.
        _sync_metas = {
            '_ultimo_usuario_manual': row_dict.get('_ultimo_usuario_manual'),
            '_fecha_ultima_act_manual': row_dict.get('_fecha_ultima_act_manual'),
            'EDITADO POR': row_dict.get('EDITADO POR'),
            'FECHA CAMBIO ESTADO': row_dict.get('FECHA CAMBIO ESTADO'),
            'GESTOR': row_dict.get('GESTOR'),
        }
        _flm_sync_campos(pid, key_val, {field: value}, _sync_metas)
        db.session.commit()
        
        # Inject KPI calculations for instant feedback
        rows_injected, _ = inject_kpis(pid, [row_dict])
        final_row = rows_injected[0]
        
        # Update schema if new tracking columns
        config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        if config_schema:
            schema_cols = set(json.loads(config_schema.valor))
            nuevas_cols = {'_ultimo_usuario_manual', '_fecha_ultima_act_manual', 'EDITADO POR'}
            if not nuevas_cols.issubset(schema_cols):
                updated_schema = list(schema_cols.union(nuevas_cols))
                config_schema.valor = safe_json_dumps(updated_schema)
                db.session.commit()
        
        return jsonify({'success': True, 'newData': final_row})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/rows/edit_key', methods=['POST'])
@login_required
def api_rows_edit_key():
    if session.get('rol') != 'zeno':
        return jsonify({'error': 'Solo Zeno puede editar la clave principal (código/WO) de un registro.'}), 403
    
    pid = session.get('current_proyecto_id')
    data = request.json
    old_key = str(data.get('old_key', '')).strip()
    new_key = str(data.get('new_key', '')).strip()
    
    if not old_key or not new_key:
        return jsonify({'error': 'Faltan datos.'}), 400
        
    if NucleusData.query.filter_by(proyecto_id=pid, key_value=new_key).first():
        return jsonify({'error': 'El nuevo código/WO ya existe.'}), 400
        
    try:
        rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=old_key).first()
        if not rec:
            return jsonify({'error': 'Registro no encontrado.'}), 404
            
        rec.key_value = new_key
        
        import json
        d = json.loads(rec.data_json)
        # Actualizar dentro del JSON si la clave vieja coincide
        for k, v in d.items():
            if str(v).strip() == old_key:
                d[k] = new_key
        rec.data_json = json.dumps(d, ensure_ascii=False)
        
        NucleusHistory.query.filter_by(proyecto_id=pid, key_value=old_key).update({'key_value': new_key})
        HistorialCambios.query.filter_by(proyecto_id=pid, key_value=old_key).update({'key_value': new_key})
        Cotizacion.query.filter_by(proyecto_id=pid, key_value=old_key).update({'key_value': new_key})

        # FLM <-> FLM - ENTEL: renombrar el mismo CM en el proyecto hermano para
        # no perder el vínculo de sincronización entre ambos.
        _rec_her = _flm_registro_hermano(pid, old_key)
        if _rec_her is not None:
            _rec_her.key_value = new_key
            try:
                _d_her = json.loads(_rec_her.data_json)
            except Exception:
                _d_her = {}
            for k, v in _d_her.items():
                if str(v).strip() == old_key:
                    _d_her[k] = new_key
            _rec_her.data_json = json.dumps(_d_her, ensure_ascii=False)
            NucleusHistory.query.filter_by(proyecto_id=_rec_her.proyecto_id, key_value=old_key).update({'key_value': new_key})
            HistorialCambios.query.filter_by(proyecto_id=_rec_her.proyecto_id, key_value=old_key).update({'key_value': new_key})
            Cotizacion.query.filter_by(proyecto_id=_rec_her.proyecto_id, key_value=old_key).update({'key_value': new_key})
        
        db.session.commit()
        return jsonify({'success': True, 'new_key': new_key})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/rows/add', methods=['POST'])
@login_required
def api_rows_add():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'contrata':
        return jsonify({'error': 'El rol Contrata no puede añadir nuevos registros.'}), 403
    _proy_chk = db.session.get(Proyecto, pid)
    if _proy_chk and _proy_chk.nombre.strip() == 'SITE' and session.get('rol') not in ('zeno', 'suport', 'supervisor'):
        return jsonify({'error': 'Solo supervisor o admin puede añadir sites.'}), 403
    try:
        data = request.json
        key_val = str(data.get('key', '')).strip()
        
        # Auto-generate key if none provided (proyecto sin clave primaria definida)
        if not key_val:
            existing = NucleusData.query.filter_by(proyecto_id=pid).all()
            nums = []
            for rec in existing:
                try:
                    nums.append(int(float(rec.key_value)))
                except (ValueError, TypeError):
                    pass
            key_val = str(max(nums) + 1) if nums else '1'
        else:
            # Check duplicate
            exists = NucleusData.query.filter_by(proyecto_id=pid, key_value=key_val).first()
            if exists: return jsonify({'error': f'El registro con ID {key_val} ya existe.'}), 400
        
        # Create record (with optional full data)
        row_data = data.get('data') or {}
        if not isinstance(row_data, dict):
            row_data = {}

        # Combustible: forzar GESTOR = usuario que registra y validar saldo en GASTO.
        proy_obj = db.session.get(Proyecto, pid)
        proy_nombre = proy_obj.nombre.strip() if proy_obj and proy_obj.nombre else ''
        if session.get('rol') == 'contrata' and proy_nombre in ('FLM', 'FLM - ENTEL', 'PEXT'):
            return jsonify({'error': 'El rol Contrata no puede crear WOs nuevos: solo completa la información de los existentes.'}), 403
        if proy_nombre == 'Combustible':
            row_data['GESTOR'] = session.get('username', '')
            mov = str(row_data.get('MOVIMIENTO', '')).strip().upper()
            gen = str(row_data.get('QR ASIGNADO', '')).strip()
            gal = row_data.get('GALONES')
            if mov == 'GASTO':
                try:
                    gal_n = float(str(gal or '').replace(',', '.').strip())
                except (ValueError, TypeError):
                    return jsonify({'error': 'Ingrese la cantidad de GALONES.'}), 400
                if not gen:
                    return jsonify({'error': 'Seleccione el QR ASIGNADO.'}), 400
                # Validación cronológica: el gasto no puede dejar en negativo
                # ningún punto del historial del generador (ni siquiera con
                # fecha anterior a otros movimientos ya registrados).
                row_data['FECHA'] = _combustible_fecha_norm(row_data.get('FECHA', ''))
                ok_g, info_g = _combustible_validar_gasto(
                    pid, gen, row_data.get('FECHA', ''), gal_n)
                if not ok_g:
                    return jsonify({'error': (
                        'No hay saldo disponible para este gasto. '
                        f"QR {gen}: al {info_g.get('fecha', '')} el saldo quedaría en "
                        f"{info_g.get('saldo', 0):g} galones. Se intentó gastar: {gal_n:g}. "
                        'Registre primero el INGRESO correspondiente.')}), 400

        # Cotizaciones: GESTOR automático y N° COTIZACION maleable (solo se fija al generar)
        if proy_nombre == 'Cotizaciones':
            import re
            from datetime import datetime as _dt
            row_data['GESTOR'] = session.get('username', '')
            if not str(row_data.get('CLIENTE', '') or '').strip():
                row_data['CLIENTE'] = 'ENTEL'
            yr = str(_dt.now().year)
            user_coti = str(row_data.get('N° COTIZACION', '') or '').strip()
            # Si el usuario proveyó un N° válido y no duplicado, respétalo (maleable)
            if user_coti and re.match(r'^HW-\d{4}-\d{7}$', user_coti):
                if not NucleusData.query.filter_by(proyecto_id=pid, key_value=user_coti).first():
                    key_val = user_coti
                    row_data['N° COTIZACION'] = key_val
                else:
                    # Duplicado -> genera siguiente
                    user_coti = ''
            if not user_coti or not re.match(r'^HW-\d{4}-\d{7}$', user_coti):
                # Genera siguiente solo si no hay uno válido (al guardar sin generar, puede quedar vacío y se asignará al generar)
                # Si viene vacío, genera igual para mantener llave única
                cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_seq').first()
                try:
                    cfg_n = int(str(cfg.valor).strip()) if cfg and cfg.valor and str(cfg.valor).strip().isdigit() else 30
                except Exception:
                    cfg_n = 30
                maxn = max(29, cfg_n - 1)
                for rec in NucleusData.query.filter_by(proyecto_id=pid).all():
                    try:
                        d2 = json.loads(rec.data_json)
                        k2 = str(d2.get('N° COTIZACION', '') or rec.key_value or '')
                        m = re.match(r'^HW-(\d{4})-(\d{7})$', k2)
                        if m and m.group(1) == yr:
                            n = int(m.group(2))
                            if n > maxn:
                                maxn = n
                    except Exception:
                        continue
                next_n = maxn + 1
                key_val = f"HW-{yr}-{next_n:07d}"
                row_data['N° COTIZACION'] = key_val
                while NucleusData.query.filter_by(proyecto_id=pid, key_value=key_val).first():
                    next_n += 1
                    key_val = f"HW-{yr}-{next_n:07d}"
                    row_data['N° COTIZACION'] = key_val
                try:
                    nxt_val = str(next_n + 1)
                    if cfg:
                        cfg.valor = nxt_val
                    else:
                        db.session.add(AppConfig(proyecto_id=pid, clave='cotizacion_next_seq', valor=nxt_val))
                except Exception:
                    pass
            else:
                key_val = user_coti

        # N° ORDEN correlativo para Cotizaciones y Combustible (siempre recalculado)
        if proy_nombre in ('Cotizaciones', 'Combustible'):
            max_ord = 0
            for rec in NucleusData.query.filter_by(proyecto_id=pid).all():
                try:
                    d2 = json.loads(rec.data_json)
                    v = str(d2.get('N° ORDEN', '') or '').strip()
                    if v.isdigit():
                        max_ord = max(max_ord, int(v))
                except Exception:
                    continue
            row_data['N° ORDEN'] = str(max_ord + 1)

        # Alta manual de WO (FLM/PEXT) por el gestor: exige el CM, fija CATEGORY,
        # aplica TablaMaestra (ej: Hrs Respuesta según Fault Level) y deja rastro
        # en historial + esquema para que el WO se consolide en tabla/KPIs.
        if proy_nombre in ('FLM', 'FLM - ENTEL', 'PEXT'):
            if not key_val:
                return jsonify({'error': 'Ingrese el Número de WO (ej: CM-20260719-00000014).'}), 400
            if not str(row_data.get('CATEGORY', '') or '').strip():
                row_data['CATEGORY'] = 'O&M CRM' if proy_nombre in ('FLM', 'FLM - ENTEL') else 'O&M PEXT'
            pk_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
            pk_col = str(pk_cfg.valor or '').strip() if pk_cfg else ''
            if pk_col:
                row_data[pk_col] = key_val
            row_data['_ultimo_usuario_manual'] = session.get('username', '')
            row_data['_fecha_ultima_act_manual'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            row_data['EDITADO POR'] = session.get('username', '')
            # FLM/PEXT: GESTOR = quien registra/edita; el admin no cuenta.
            if proy_nombre in ('FLM', 'FLM - ENTEL', 'PEXT') and session.get('rol') not in ('zeno', 'suport'):
                row_data['GESTOR'] = session.get('username', '')
            for t in TablaMaestra.query.filter_by(proyecto_id=pid).all():
                t_cols = [c.strip() for c in t.columna_criterio.split(',')]
                t_vals = [v.strip() for v in t.valor_criterio.split(',')]
                if all(str(row_data.get(c, '')) == v for c, v in zip(t_cols, t_vals)):
                    row_data[t.nueva_columna] = t.nuevo_valor

        # Proyectos manuales (Material, Dataper, SITE, Generadores, etc.): la PK debe quedar
        # también dentro del JSON, no solo como key_value. /api/wo/meta y otros lectores
        # hacen d.get('COD_MATERIAL') — si no está, el desplegable sale sin [código].
        if proy_nombre not in ('FLM', 'FLM - ENTEL', 'PEXT'):
            try:
                _pk_cfg2 = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
                _pk_col2 = str(_pk_cfg2.valor or '').strip() if _pk_cfg2 else ''
                if _pk_col2 and _pk_col2 not in row_data:
                    row_data[_pk_col2] = key_val
            except Exception:
                pass

        new_record = NucleusData(proyecto_id=pid, key_value=key_val, data_json=json.dumps(row_data))
        db.session.add(new_record)
        db.session.commit()

        if proy_nombre in ('FLM', 'FLM - ENTEL', 'PEXT'):
            db.session.add(HistorialCambios(
                proyecto_id=pid, usuario_id=session.get('user_id'), username=session.get('username'),
                key_value=key_val, campo_modificado='CREACIÓN',
                valor_anterior='', valor_nuevo=key_val, fecha=datetime.utcnow()))
            schema_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
            try:
                schema_cols = set(json.loads(schema_cfg.valor) if schema_cfg and schema_cfg.valor else [])
            except Exception:
                schema_cols = set()
            nuevas = {k for k in row_data.keys()
                      if k and not str(k).startswith('_') and not str(k).startswith('KPI_')
                      and not str(k).startswith('COTIZACION_') and k != 'MATERIALES'}
            if not nuevas.issubset(schema_cols):
                merged = schema_cols.union(nuevas)
                if schema_cfg:
                    schema_cfg.valor = safe_json_dumps(list(merged))
                else:
                    db.session.add(AppConfig(proyecto_id=pid, clave='app_schema', valor=safe_json_dumps(list(merged))))
            db.session.commit()

        return jsonify({'success': True, 'key': key_val})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/rows/delete', methods=['POST'])
@login_required
def api_rows_delete():
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'No tienes permisos para eliminar registros. Solo Zeno y Suport pueden hacerlo.'}), 403
    
    pid = session.get('current_proyecto_id')
    if not pid: return jsonify({'error': 'No hay proyecto seleccionado'}), 400
    
    proy = Proyecto.query.get(pid)
    proy_nombre = proy.nombre if proy else ''
    
    try:
        data = request.json
        keys = data.get('keys', [])
        if not isinstance(keys, list):
            return jsonify({'error': 'Formato inválido: keys debe ser una lista.'}), 400
        # Normalizar: strings no vacíos, sin duplicados
        keys = [str(k).strip() for k in keys if str(k or '').strip()]
        keys = list(dict.fromkeys(keys))  # dedup preservando orden
        if not keys: return jsonify({'error': 'No se especificaron registros para eliminar'}), 400
        
        # Combustible: eliminar un INGRESO (o cualquier movimiento) no puede
        # dejar en negativo el historial del generador.
        if proy_nombre == 'Combustible':
            _a_borrar = NucleusData.query.filter(
                NucleusData.proyecto_id == pid, NucleusData.key_value.in_(keys)).all()
            _por_gen = {}
            for _r in _a_borrar:
                try:
                    _d = json.loads(_r.data_json)
                except Exception:
                    continue
                _g = str(_d.get('QR ASIGNADO', '')).strip()
                if _g:
                    _por_gen.setdefault(_g, set()).add(str(_r.key_value))
            for _g, _keys_g in _por_gen.items():
                _filas = [f for f in _combustible_filas_gen(pid, _g)
                          if str(f.get('key')) not in _keys_g]
                _ok, _info = _combustible_chequear(_filas)
                if not _ok:
                    return jsonify({'error': (
                        'No se puede eliminar: ese movimiento sostiene el saldo del '
                        f"QR {_g}. Al {_info.get('fecha', '')} el saldo quedaría en "
                        f"{_info.get('saldo', 0):g} galones. "
                        'Elimine primero los GASTOS posteriores que dependen de él.')}), 400

        # Delete records
        NucleusData.query.filter(NucleusData.proyecto_id == pid, NucleusData.key_value.in_(keys)).delete(synchronize_session=False)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/rows/bulk_update', methods=['POST'])
@login_required
def api_rows_bulk_update():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para actualizar datos.'}), 403
    try:
        data = request.json
        key_val = data.get('key')
        updates = data.get('data')
        if not key_val or not isinstance(updates, dict):
            return jsonify({'error': 'Datos incompletos'}), 400
        record = NucleusData.query.filter_by(proyecto_id=pid, key_value=str(key_val)).first()
        if not record: return jsonify({'error': 'Registro no encontrado'}), 404
        row_dict = json.loads(record.data_json)
        old_state = str(row_dict.get('Estado de la tarea (WO State)', '')).strip()

        # Combustible: la edición masiva tampoco puede dejar saldos negativos.
        _proy_bulk = db.session.get(Proyecto, pid) if pid else None
        _proy_bulk_nombre = _proy_bulk.nombre.strip() if _proy_bulk and _proy_bulk.nombre else ''

        # WO enviado a aprobación: el rol Contrata ya no puede modificarlo.
        if (session.get('rol') == 'contrata' and _proy_bulk_nombre in ('FLM', 'FLM - ENTEL', 'PEXT')
                and str(row_dict.get('_ENVIADO_APROBACION', '')).strip() == '1'):
            return jsonify({'error': 'Este WO ya fue enviado a aprobaci\u00f3n y no puede editarse. Contacta al personal administrativo.'}), 403

        # PEXT: fila finalizada → solo zeno/suport/supervisor pueden editar
        if (_proy_bulk_nombre in ('PEXT', 'FLM', 'FLM - ENTEL')
                and str(row_dict.get('CATEGORY', '')).strip() == 'O&M PEXT'
                and str(row_dict.get('_FINALIZADO', '')).strip() == '1'
                and session.get('rol') not in ('zeno', 'suport', 'supervisor')):
            return jsonify({'error': 'Este WO est\u00e1 finalizado y no puede editarse. Contacta al supervisor o administrador.'}), 403

        # Bitácora es solo para el personal (admin/supervisor/gestor), no para Contrata:
        # el rol Contrata jamás envía ni modifica BITACORA / entradas de bitácora.
        if session.get('rol') == 'contrata':
            updates.pop('BITACORA', None)
            updates.pop('_BITACORA_ENTRY', None)

        # PEXT: cada guardado con texto en Bitácora agrega una entrada {texto, usuario,
        # fecha} a la pestaña Bitácora. La clave se consume siempre (sin persistirse).
        if '_BITACORA_ENTRY' in updates:
            _bit_txt = str(updates.pop('_BITACORA_ENTRY') or '').strip()
            if (_proy_bulk_nombre in ('PEXT', 'FLM', 'FLM - ENTEL')
                and str(row_dict.get('CATEGORY', '')).strip() == 'O&M PEXT'
                and _bit_txt):
                _entradas = row_dict.get('_BITACORA_ENTRIES')
                if isinstance(_entradas, str):
                    try:
                        _entradas = json.loads(_entradas)
                    except Exception:
                        _entradas = []
                if not isinstance(_entradas, list):
                    _entradas = []
                _entradas.append({
                    'texto': _bit_txt,
                    'usuario': session.get('username') or '',
                    'fecha': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
                row_dict['_BITACORA_ENTRIES'] = _entradas

        if _proy_bulk_nombre == 'Combustible' and any(
                k in ('MOVIMIENTO', 'GALONES', 'QR ASIGNADO', 'FECHA') for k in updates.keys()):
            _old_gen = str(row_dict.get('QR ASIGNADO', '')).strip()
            _new_gen = str(updates.get('QR ASIGNADO', row_dict.get('QR ASIGNADO', ''))).strip()
            _new_mov = str(updates.get('MOVIMIENTO', row_dict.get('MOVIMIENTO', ''))).strip().upper()
            _new_gal = _parse_galones(updates.get('GALONES', row_dict.get('GALONES')))
            _new_fec = _combustible_fecha_norm(updates.get('FECHA', row_dict.get('FECHA', '')))
            if 'FECHA' in updates:
                updates['FECHA'] = _new_fec
            _nuevo = {'key': str(key_val), 'fecha': _new_fec, 'mov': _new_mov, 'gal': _new_gal}
            for _g in ({_old_gen, _new_gen} - {''}):
                _filas = [f for f in _combustible_filas_gen(pid, _g)
                          if str(f.get('key')) != str(key_val)]
                if _g == _new_gen and _new_gen:
                    _filas.append(dict(_nuevo))
                    _filas.sort(key=lambda f: (_combustible_fecha_ord(f['fecha']), str(f.get('key') or '')))
                _ok, _info = _combustible_chequear(_filas)
                if not _ok:
                    return jsonify({'error': (
                        'No hay saldo disponible para este cambio. '
                        f"QR {_g}: al {_info.get('fecha', '')} el saldo quedaría en "
                        f"{_info.get('saldo', 0):g} galones.")}), 400

        for field, value in updates.items():
            valor_anterior = row_dict.get(field, '')
            if str(valor_anterior) != str(value):
                historial = HistorialCambios(
                    proyecto_id=pid,
                    usuario_id=session.get('user_id'),
                    username=session.get('username'),
                    key_value=str(key_val),
                    campo_modificado=field,
                    valor_anterior=str(valor_anterior),
                    valor_nuevo=str(value)
                )
                db.session.add(historial)
            row_dict[field] = value
        row_dict['_ultimo_usuario_manual'] = session.get('username')
        row_dict['_fecha_ultima_act_manual'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        row_dict['EDITADO POR'] = session.get('username')
        # FLM/PEXT: GESTOR = quien presiona Guardar; el admin no cuenta.
        if _proy_bulk_nombre in ('FLM', 'FLM - ENTEL', 'PEXT') and session.get('rol') not in ('zeno', 'suport'):
            row_dict['GESTOR'] = session.get('username')

        new_state = str(row_dict.get('Estado de la tarea (WO State)', '')).strip()
        if new_state and new_state != old_state:
            row_dict['FECHA CAMBIO ESTADO'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        # --- Instant Logic: TablaMaestra ---
        tablas = TablaMaestra.query.filter_by(proyecto_id=pid).all()
        for t in tablas:
            t_cols = [c.strip() for c in t.columna_criterio.split(',')]
            t_vals = [v.strip() for v in t.valor_criterio.split(',')]
            match = True
            for c, v in zip(t_cols, t_vals):
                if str(row_dict.get(c, '')) != v:
                    match = False
                    break
            if match:
                row_dict[t.nueva_columna] = t.nuevo_valor

        # --- Instant Logic: Reglas de Estado Manual ---
        reglas_manuales = ReglaEstadoManual.query.filter_by(proyecto_id=pid).all()
        for r in reglas_manuales:
            r_cols = [c.strip() for c in r.columna_criterio.split(',')]
            r_vals = [v.strip() for v in r.valor_criterio.split(',')]
            match = True
            for c, v in zip(r_cols, r_vals):
                if str(row_dict.get(c, '')) != v:
                    match = False
                    break
            if match:
                row_dict[r.columna_manual] = r.nuevo_valor

        record.data_json = safe_json_dumps(row_dict)
        # FLM <-> FLM - ENTEL: propaga al CM espejo los campos editados del payload
        # (solo los propagables), para que la información/fotos se reflejen en el
        # otro proyecto sin pisar columnas de esquema propio.
        _flm_sync_campos(pid, key_val, updates, {
            '_ultimo_usuario_manual': row_dict.get('_ultimo_usuario_manual'),
            '_fecha_ultima_act_manual': row_dict.get('_fecha_ultima_act_manual'),
            'EDITADO POR': row_dict.get('EDITADO POR'),
            'FECHA CAMBIO ESTADO': row_dict.get('FECHA CAMBIO ESTADO'),
            'GESTOR': row_dict.get('GESTOR'),
        })
        db.session.commit()

        rows_injected, _ = inject_kpis(pid, [row_dict])
        final_row = rows_injected[0]

        # Update schema if new tracking columns
        config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        if config_schema:
            schema_cols = set(json.loads(config_schema.valor))
            nuevas_cols = {'_ultimo_usuario_manual', '_fecha_ultima_act_manual', 'FECHA CAMBIO ESTADO', 'EDITADO POR'}
            if not nuevas_cols.issubset(schema_cols):
                updated_schema = list(schema_cols.union(nuevas_cols))
                config_schema.valor = safe_json_dumps(updated_schema)
                db.session.commit()

        return jsonify({'success': True, 'newData': final_row})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/rows/finalizar', methods=['POST'])
@login_required
def api_rows_finalizar():
    """Finaliza (o revierte) un WO de PEXT. Guarda _FINALIZADO='1'/'0' en data_json.
    Revertir solo lo puede hacer zeno/suport/supervisor."""
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos.'}), 403
    try:
        data = request.json
        key_val = data.get('key')
        finalizado = data.get('finalizado', True)  # True = finalizar, False = revertir
        if not key_val:
            return jsonify({'error': 'Falta la clave del registro.'}), 400

        # Solo proyecto PEXT (o FLM - ENTEL, donde viven hoy las filas PEXT migradas)
        proy = db.session.get(Proyecto, pid)
        if not proy or proy.nombre.strip() not in ('PEXT', 'FLM', 'FLM - ENTEL'):
            return jsonify({'error': 'Esta acci\u00f3n solo est\u00e1 disponible en los proyectos PEXT/FLM.'}), 403

        # Revertir: solo roles privilegiados
        if not finalizado and session.get('rol') not in ('zeno', 'suport', 'supervisor'):
            return jsonify({'error': 'Solo el supervisor o administrador puede desbloquear un WO finalizado.'}), 403

        record = NucleusData.query.filter_by(proyecto_id=pid, key_value=str(key_val)).first()
        if not record:
            return jsonify({'error': 'Registro no encontrado.'}), 404

        row_dict = json.loads(record.data_json)
        nuevo_estado = '1' if finalizado else '0'
        estado_anterior = str(row_dict.get('_FINALIZADO', '0')).strip()

        if estado_anterior == nuevo_estado:
            return jsonify({'success': True, 'newData': row_dict, 'message': 'Sin cambios.'})  # idempotente

        # Historial
        historial = HistorialCambios(
            proyecto_id=pid,
            usuario_id=session.get('user_id'),
            username=session.get('username'),
            key_value=str(key_val),
            campo_modificado='_FINALIZADO',
            valor_anterior=estado_anterior,
            valor_nuevo=nuevo_estado
        )
        db.session.add(historial)

        row_dict['_FINALIZADO'] = nuevo_estado
        row_dict['_FINALIZADO_POR'] = session.get('username') if finalizado else ''
        row_dict['_FINALIZADO_FECHA'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') if finalizado else ''
        record.data_json = safe_json_dumps(row_dict)
        db.session.commit()

        rows_injected, _ = inject_kpis(pid, [row_dict])
        return jsonify({'success': True, 'newData': rows_injected[0]})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500