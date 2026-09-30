# -*- coding: utf-8 -*-
import os, io, re, json, time, glob, zipfile, gzip, mimetypes, tempfile, csv
import urllib.request
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


bp = Blueprint('admin', __name__)



@bp.route('/api/debug/dataper', methods=['GET'])
@login_required
def api_debug_dataper():
    """Diagnóstico de Dataper: muestra cuántos técnicos hay y sus valores de ESTADO."""
    if session.get('rol') not in ['zeno', 'suport']:
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        dataper = Proyecto.query.filter_by(nombre='Dataper').first()
        if not dataper:
            return jsonify({'error': 'Proyecto Dataper no existe en la BD', 'dataper_id': None})
        rows = NucleusData.query.filter_by(proyecto_id=dataper.id).all()
        total = len(rows)
        estado_counter = {}
        tecnicos_activos = []
        for r in rows:
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            est = str(d.get('ESTADO') or '').strip() or '(vacío)'
            estado_counter[est] = estado_counter.get(est, 0) + 1
            est_up = est.upper()
            if est_up in ('ACTIVO', '(VACÍO)', ''):
                tec = str(d.get('TECNICO') or '').strip()
                if tec:
                    tecnicos_activos.append({'tecnico': tec, 'contrata': str(d.get('CONTRATA') or ''), 'estado': est})
        return jsonify({
            'dataper_id': dataper.id,
            'total_filas': total,
            'estado_distribucion': estado_counter,
            'tecnicos_activos_count': len(tecnicos_activos),
            'muestra_tecnicos': tecnicos_activos[:20],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/admin/proyecto', methods=['POST', 'DELETE'])
@login_required
def api_admin_proyecto():
    if session.get('rol') not in ['zeno', 'suport']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar proyectos.'}), 403
    
    if request.method == 'POST':
        data = request.json
        nombre = data.get('nombre', '').strip()
        if not nombre: return jsonify({'error': 'Nombre requerido'}), 400
        try:
            nuevo = Proyecto(nombre=nombre, descripcion=data.get('descripcion', ''), icono=data.get('icono', 'fa-folder-open'))
            db.session.add(nuevo)
            db.session.commit()
            return jsonify({'success': True, 'id': nuevo.id})
        except:
            return jsonify({'error': 'Nombre duplicado'}), 400
            
    if request.method == 'DELETE':
        pid = request.json.get('id')
        if not pid: return jsonify({'error': 'ID requerido'}), 400
        p = db.session.get(Proyecto, pid)
        if p and p.nombre in ('FLM', 'FLM - ENTEL', 'PEXT', 'Dataper', 'Material'):
            return jsonify({'error': 'Los proyectos FLM, FLM - ENTEL, PEXT, Dataper y Material no se pueden eliminar.'}), 403
        try:
            # Cascading delete manually for safety (or set up models with cascade)
            # We must not delete the project 1 (Pangeaco) if it's the only one or a protected one?
            # User choice, I'll allow deleting any.
            Tecnico.query.filter_by(proyecto_id=pid).delete()
            NucleusData.query.filter_by(proyecto_id=pid).delete()
            AppConfig.query.filter_by(proyecto_id=pid).delete()
            FiltroMaestro.query.filter_by(proyecto_id=pid).delete()
            TablaMaestra.query.filter_by(proyecto_id=pid).delete()
            
            p = db.session.get(Proyecto, pid)
            if p:
                db.session.delete(p)
                db.session.commit()
                # If deleted project is active project, clear it
                if session.get('current_proyecto_id') == int(pid):
                    session.pop('current_proyecto_id', None)
                    session.pop('current_proyecto_nombre', None)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@bp.route('/api/tecnicos', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_tecnicos():
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Unauthorized'}), 403

    if request.method == 'GET':
        pid = request.args.get('proyecto_id', type=int)
        q = Tecnico.query
        if pid:
            q = q.filter_by(proyecto_id=pid)
        return jsonify([{
            'id': t.id,
            'proyecto_id': t.proyecto_id,
            'nombre': t.nombre,
            'contrata': t.contrata,
            'especialidad': t.especialidad,
            'telefono': t.telefono
        } for t in q.order_by(Tecnico.nombre).all()])

    if request.method == 'POST':
        data = request.json
        pid = data.get('proyecto_id')
        nombre = (data.get('nombre') or '').strip()
        if not pid or not nombre:
            return jsonify({'error': 'Proyecto y nombre requeridos'}), 400
        nuevo = Tecnico(
            proyecto_id=pid,
            nombre=nombre,
            contrata=(data.get('contrata') or '').strip(),
            especialidad=(data.get('especialidad') or '').strip(),
            telefono=(data.get('telefono') or '').strip()
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({'success': True, 'id': nuevo.id})

    if request.method == 'DELETE':
        tid = request.json.get('id')
        if not tid:
            return jsonify({'error': 'ID requerido'}), 400
        t = db.session.get(Tecnico, tid)
        if not t:
            return jsonify({'error': 'No encontrado'}), 404
        db.session.delete(t)
        db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/admin/usuario', methods=['POST', 'PUT', 'DELETE'])
@login_required
def api_admin_usuario():
    if session.get('rol') not in ['zeno', 'suport']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar usuarios.'}), 403
        
    if request.method == 'POST':
        data = request.json
        nombre = data.get('nombre', '').strip()
        user = data.get('username', '').strip()
        pw = data.get('password', '').strip()
        rol = data.get('rol', 'supervisor').strip()
        proyectos = data.get('proyectos', [])
        if not all([user, pw]): return jsonify({'error': 'Datos incompletos'}), 400
        if rol.strip().lower() in ('gestor', 'contrata') and not proyectos:
            return jsonify({'error': 'El rol Gestor/Contrata requiere al menos un módulo asignado.'}), 400
        try:
            nuevo = Usuario(username=user, password_hash=generate_password_hash(pw), rol=rol, nombre=nombre)
            db.session.add(nuevo)
            db.session.flush()
            for pid in proyectos:
                db.session.add(AccesoProyecto(usuario_id=nuevo.id, proyecto_id=int(pid), restricciones='{}'))
            db.session.commit()
            return jsonify({'success': True, 'id': nuevo.id})
        except:
            db.session.rollback()
            return jsonify({'error': 'Usuario duplicado'}), 400
            
    if request.method == 'PUT':
        data = request.json
        uid = data.get('id')
        nombre = data.get('nombre', '').strip()
        user = data.get('username', '').strip()
        pw = data.get('password', '').strip()
        rol = data.get('rol', '').strip()
        proyectos = data.get('proyectos')
        
        if not uid or not user: return jsonify({'error': 'ID y usuario requeridos'}), 400
        if rol.strip().lower() in ('gestor', 'contrata') and proyectos == []:
            return jsonify({'error': 'El rol Gestor/Contrata requiere al menos un módulo asignado.'}), 400
        try:
            u = db.session.get(Usuario, uid)
            if not u: return jsonify({'error': 'Usuario no encontrado'}), 404
            if session.get('rol') == 'suport' and u.rol == 'zeno':
                return jsonify({'error': 'El rol Suport no puede editar a un usuario Zeno.'}), 403
            
            u.nombre = nombre
            u.username = user
            if pw:
                u.password_hash = generate_password_hash(pw)
            if rol:
                u.rol = rol
                
            if proyectos is not None:
                AccesoProyecto.query.filter_by(usuario_id=uid).delete()
                for pid in proyectos:
                    db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=int(pid), restricciones='{}'))
                
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Usuario duplicado o error: ' + str(e)}), 400
            
    if request.method == 'DELETE':
        if session.get('rol') != 'zeno':
            return jsonify({'error': 'Solo Zeno puede eliminar usuarios.'}), 403
        uid = request.json.get('id')
        if not uid: return jsonify({'error': 'ID requerido'}), 400
        if int(uid) == session.get('user_id'):
            return jsonify({'error': 'No puedes borrar tu propio usuario'}), 400
        try:
            u = db.session.get(Usuario, uid)
            if u:
                # Nullify history records referencing this user (FK nullable)
                HistorialCambios.query.filter_by(usuario_id=uid).update({'usuario_id': None})
                # Delete project access permissions
                AccesoProyecto.query.filter_by(usuario_id=uid).delete()
                db.session.delete(u)
                db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


@bp.route('/api/admin/usuario/duplicar', methods=['POST'])
@login_required
def api_admin_usuario_duplicar():
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo Zeno y Suport pueden duplicar usuarios.'}), 403
        
    data = request.json
    src_id = data.get('source_id')
    new_user = data.get('new_username', '').strip()
    new_pw = data.get('new_password', '').strip()
    
    if not all([src_id, new_user, new_pw]):
        return jsonify({'error': 'Datos incompletos para duplicar'}), 400
        
    src_u = db.session.get(Usuario, src_id)
    if not src_u: 
        return jsonify({'error': 'Usuario origen no encontrado'}), 404
        
    try:
        nuevo = Usuario(username=new_user, password_hash=generate_password_hash(new_pw), rol=src_u.rol)
        db.session.add(nuevo)
        db.session.flush() # Para obtener el nuevo ID
        
        # Copiar permisos (AccesoProyecto)
        permisos = AccesoProyecto.query.filter_by(usuario_id=src_id).all()
        for p in permisos:
            new_p = AccesoProyecto(usuario_id=nuevo.id, proyecto_id=p.proyecto_id, restricciones=p.restricciones)
            db.session.add(new_p)
            
        db.session.commit()
        return jsonify({'success': True, 'id': nuevo.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Error al duplicar (¿Usuario duplicado?): ' + str(e)}), 400


@bp.route('/api/admin/permisos', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_admin_permisos():
    if session.get('rol') not in ['zeno', 'suport']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar permisos.'}), 403
    
    if request.method == 'GET':
        uid = request.args.get('uid')
        if not uid: return jsonify([])
        permisos = AccesoProyecto.query.filter_by(usuario_id=uid).all()
        result = []
        for p in permisos:
            proj = db.session.get(Proyecto, p.proyecto_id)
            result.append({
                'id': p.id,
                'proyecto_id': p.proyecto_id,
                'proyecto_nombre': proj.nombre if proj else 'Desconocido',
                'restricciones': p.restricciones
            })
        return jsonify(result)

    if request.method == 'POST':
        data = request.json
        uid = data.get('usuario_id')
        pid = data.get('proyecto_id')
        res = data.get('restricciones', '{}')
        if not uid or not pid: return jsonify({'error': 'Faltan datos'}), 400
        
        existente = AccesoProyecto.query.filter_by(usuario_id=uid, proyecto_id=pid).first()
        if existente:
            existente.restricciones = res
        else:
            nuevo = AccesoProyecto(usuario_id=uid, proyecto_id=pid, restricciones=res)
            db.session.add(nuevo)
        db.session.commit()
        return jsonify({'success': True})

    if request.method == 'DELETE':
        aid = request.json.get('id')
        acc = db.session.get(AccesoProyecto, aid)
        if acc:
            db.session.delete(acc)
            db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/admin/columnas')
@login_required
def api_admin_columnas():
    if session.get('rol') not in ['zeno', 'suport']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    pid = request.args.get('pid')
    if not pid: return jsonify([])
    
    # Standard columns
    schema_config = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
    cols = json.loads(schema_config.valor) if schema_config else []
    
    # Manual columns
    manual_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    if manual_cfg:
        m_cols = json.loads(manual_cfg.valor)
        for mc in m_cols:
            if mc['nombre'] not in cols:
                cols.append(mc['nombre'])
                
    return jsonify(sorted(cols))


@bp.route('/api/admin/column_values')
@login_required
def api_column_values():
    pid_arg = request.args.get('pid')
    pid = pid_arg if pid_arg else session.get('current_proyecto_id')
    col = request.args.get('col')
    if not pid or not col: return jsonify([])
    
    # Get unique values from NucleusData
    rows = NucleusData.query.filter_by(proyecto_id=pid).all()
    vals = set()
    for r in rows:
        d = json.loads(r.data_json)
        v = d.get(col)
        if v: vals.add(str(v).strip())
    
    return jsonify(sorted(list(vals)))


@bp.route('/api/admin/export_zip', methods=['GET'])
@login_required
def api_admin_export_zip():
    """Respaldo completo de la DB (solo datos, las fotos son archivos y no se incluyen).
    Solo admin. Descarga un ZIP con un JSON por tabla + manifest con conteos.
    Se excluye token_store (secretos) a propósito."""
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo admin'}), 403
    import zipfile
    modelos = {
        'usuarios': Usuario, 'proyectos': Proyecto, 'app_config': AppConfig,
        'nucleus_data': NucleusData, 'nucleus_history': NucleusHistory,
        'filtros_maestros': FiltroMaestro, 'tablas_maestras': TablaMaestra,
        'reglas_estado_manual': ReglaEstadoManual,
        'accesos_proyecto': AccesoProyecto, 'kpi_configs': KpiConfig,
        'historial_cambios': HistorialCambios, 'tecnicos': Tecnico,
        'cotizaciones': Cotizacion,
    }
    fd, ruta = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    manifest = {'tablas': {}, 'proyecto_por_id': {}}
    try:
        for p in Proyecto.query.all():
            manifest['proyecto_por_id'][str(p.id)] = p.nombre
        with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as zf:
            for nombre, modelo in modelos.items():
                tiene_pid = hasattr(modelo, 'proyecto_id')
                if tiene_pid:
                    pids = [r[0] for r in db.session.query(modelo.proyecto_id).distinct().all()]
                    total = 0
                    for _pid in pids:
                        fil = []
                        q = modelo.query.filter_by(proyecto_id=_pid).order_by(modelo.id)
                        offset = 0
                        while True:
                            lote = q.offset(offset).limit(2000).all()
                            if not lote:
                                break
                            for obj in lote:
                                d = {}
                                for col in modelo.__table__.columns:
                                    v = getattr(obj, col.name)
                                    if isinstance(v, datetime):
                                        v = v.strftime('%Y-%m-%d %H:%M:%S')
                                    d[col.name] = v
                                fil.append(d)
                            offset += len(lote)
                        zf.writestr(f'{nombre}_p{_pid}.json', json.dumps(fil, ensure_ascii=False))
                        total += len(fil)
                    manifest['tablas'][nombre] = total
                else:
                    fil = []
                    for obj in modelo.query.order_by(modelo.id).all():
                        d = {}
                        for col in modelo.__table__.columns:
                            v = getattr(obj, col.name)
                            if isinstance(v, datetime):
                                v = v.strftime('%Y-%m-%d %H:%M:%S')
                            d[col.name] = v
                        fil.append(d)
                    zf.writestr(f'{nombre}.json', json.dumps(fil, ensure_ascii=False))
                    manifest['tablas'][nombre] = len(fil)
            manifest['exportado_en'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
    except Exception as e:
        try:
            os.remove(ruta)
        except Exception:
            pass
        return jsonify({'error': str(e)}), 500
    nombre_zip = 'respaldo_nucleus_' + datetime.utcnow().strftime('%Y%m%d_%H%M%S') + '.zip'
    return send_from_directory(os.path.dirname(ruta), os.path.basename(ruta),
                               as_attachment=True, download_name=nombre_zip)


@bp.route('/api/admin/od_reset', methods=['POST'])
@login_required
def api_admin_od_reset():
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo admin'}), 403
    for num in (1, 2):
        TokenStore.query.filter_by(clave=_od_cuenta(num)['token_key']).delete()
    db.session.commit()
    return jsonify({'success': True, 'msg': 'Tokens OneDrive reseteados. Pon los nuevos OD_REFRESH_TOKEN en Render.'})


@bp.route('/api/config/consolidation', methods=['GET', 'POST'])
@login_required
def api_config_consolidation():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar la configuración de consolidación.'}), 403
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='consolidation_config').first()
    
    if request.method == 'GET':
        return jsonify(json.loads(config.valor) if config else {})
        
    if request.method == 'POST':
        data = request.json
        if config:
            config.valor = safe_json_dumps(data)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='consolidation_config', valor=safe_json_dumps(data)))
        db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/config/cotizacion_margen', methods=['GET', 'POST'])
@login_required
def api_config_cotizacion_margen():
    """Porcentaje de margen aplicado al Precio Cobra para calcular Precio Unid (default 30)."""
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo' and request.method != 'GET':
        return jsonify({'error': 'Rol DEMO no tiene permisos para modificar el margen de cotización.'}), 403
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_margen_pct').first()

    if request.method == 'GET':
        if config:
            try:
                return jsonify({'porcentaje': float(config.valor)})
            except Exception:
                pass
        return jsonify({'porcentaje': 30})

    if request.method == 'POST':
        data = request.json or {}
        try:
            pct = float(data.get('porcentaje', 30))
        except (TypeError, ValueError):
            return jsonify({'error': 'Porcentaje inválido'}), 400
        if pct < 0:
            return jsonify({'error': 'El porcentaje no puede ser negativo'}), 400
        if config:
            config.valor = safe_json_dumps(pct)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='cotizacion_margen_pct', valor=safe_json_dumps(pct)))
        db.session.commit()
        return jsonify({'success': True, 'porcentaje': pct})


@bp.route('/api/config/init_manual', methods=['POST'])
@login_required
def api_config_init_manual():
    pid = session.get('current_proyecto_id')
    if session.get('rol') not in ['zeno', 'suport', 'supervisor']:
        return jsonify({'error': 'No tienes permisos para inicializar proyectos.'}), 403
    try:
        data = request.json
        pk_name = str(data.get('primary_key', '')).strip()
        if not pk_name: return jsonify({'error': 'El nombre de la columna principal es requerido.'}), 400
        
        # Initialize Primary Key and empty Schema
        config_pk = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
        if config_pk:
            config_pk.valor = pk_name
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='primary_key', valor=pk_name))
            
        config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        if not config_schema:
            db.session.add(AppConfig(proyecto_id=pid, clave='app_schema', valor=json.dumps([])))
            
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


RENDICION_CSV_TEMPLATE = 'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
# Claves AppConfig usadas por el módulo Rendición:
#   rendicion_csv_url  -> URL CSV pública del Google Form
#   rendicion_sync_key -> token de sincronización (cron externo)


@bp.route('/api/rendicion/sync', methods=['GET', 'POST'])
def api_rendicion_sync():
    """Importa SOLO las filas nuevas del Google Form al módulo 'Rendicion'.

    Autorización por dos vías:
      - Botón "Sincronizar" en la web: usuario con sesión y rol admin/zeno/suport.
      - Cron externo: ?key=<rendicion_sync_key> (sin sesión).
    No toca filas existentes: solo inserta claves nuevas (Marca temporal).
    """
    key = request.args.get('key') or (request.get_json(silent=True) or {}).get('key', '')
    cfg = AppConfig.query.filter_by(clave='rendicion_sync_key').first()
    key_valida = bool(cfg and cfg.valor and key == cfg.valor)
    if not key_valida:
        rol = session.get('rol')
        autorizado_web = bool(
            session.get('user_id')
            and rol in ('admin', 'zeno', 'suport')
            and (session.get('current_proyecto_nombre') or '').strip().lower() == 'rendicion'
        )
        if not autorizado_web:
            if not key:
                return jsonify({'error': 'Falta la key de sincronización.'}), 400
            return jsonify({'error': 'Key de sincronización inválida.'}), 403

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

    # Columnas permitidas solicitadas
    permitidas = {
        'Marca temporal',
        'Nombre del proyecto',
        'Tipo de presupuesto',
        'Tipo de gasto',
        'Documento del beneficiario',
        'Técnico beneficiario',
        'Nombre de site',
        'Número CM / PM / PLM',
        'Criticidad - Prioridad',
        'Motivo de la solicitud',
        'Monto total del depósito',
        'Tipo de depósito a realizar',
        'Número de celular o CCI',
        'Titular de la cuenta',
        'Responsable de la validación',
        'Observaciones (Form)'
    }

    # Schema actual del módulo
    schema_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='app_schema').first()
    try:
        schema_cols = set(json.loads(schema_cfg.valor)) if schema_cfg and schema_cfg.valor else set()
    except Exception:
        schema_cols = set()

    nuevas = 0
    omitidas = 0
    t0 = time.time()
    for row in reader:
        datos = {}
        for f in fields:
            if f is None:
                continue
            v = (row.get(f) or '').strip()
            # Aplicar renombre
            nombre_col = renombrar.get(f, f)
            if nombre_col in permitidas:
                datos[nombre_col] = v
        
        id_sol = str(datos.get(pk_col, '') or '').strip()
        if not id_sol:
            omitidas += 1
            continue
        existe = NucleusData.query.filter_by(proyecto_id=proy.id, key_value=id_sol).first()
        if existe:
            omitidas += 1
            continue
        db.session.add(NucleusData(proyecto_id=proy.id, key_value=id_sol,
                                   data_json=safe_json_dumps(datos)))
        schema_cols.update(set(datos.keys()))
        nuevas += 1

    # Persistir schema ampliado
    if schema_cfg:
        schema_cfg.valor = safe_json_dumps(sorted(schema_cols))
    else:
        db.session.add(AppConfig(proyecto_id=proy.id, clave='app_schema',
                                 valor=safe_json_dumps(sorted(schema_cols))))
    db.session.commit()

    return jsonify({
        'success': True,
        'nuevas': nuevas,
        'omitidas_existentes': omitidas,
        'segundos': round(time.time() - t0, 2),
    })
@bp.route('/api/rendicion/sync_sustentos', methods=['POST'])
def api_rendicion_sync_sustentos():
    """Sincroniza los sustentos desde la segunda hoja de Google Sheets."""
    rol = session.get('rol')
    autorizado = bool(session.get('user_id') and rol in ('admin', 'zeno', 'suport'))
    if not autorizado:
        return jsonify({'error': 'No autorizado.'}), 403

    proy = Proyecto.query.filter_by(nombre='Rendicion').first()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404

    csv_url = 'https://docs.google.com/spreadsheets/d/18CYUhXGN8jWk4hzr194p3vhdU6H90WD-O0Aw77WxgEY/export?format=csv&gid=831408062'
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

    actualizados = 0
    omitidos = 0
    no_encontrados = 0
    t0 = time.time()
    
    for row in reader:
        cod = (row.get(col_codigo) or '').strip()
        if not cod: continue
        
        # Buscar en DB por CODIGO DEPOSITO
        all_data = NucleusData.query.filter_by(proyecto_id=proy.id).all()
        target = None
        target_dict = None
        for d in all_data:
            try:
                dj = json.loads(d.data_json)
                if str(dj.get('CODIGO DEPOSITO', '')).strip() == cod:
                    target = d
                    target_dict = dj
                    break
            except:
                pass
        
        if not target:
            no_encontrados += 1
            continue
            
        estado_actual = str(target_dict.get('ESTADO', '')).strip().upper()
        if estado_actual == 'DEPOSITADO':
            # Actualizamos estado y agregamos data
            for k, v in row.items():
                if k and k != col_codigo:
                    target_dict[f'SUSTENTO_{k.upper()}'] = str(v).strip()
            
            target_dict['ESTADO'] = 'CON SUSTENTO'
            target.data_json = safe_json_dumps(target_dict)
            actualizados += 1
        else:
            omitidos += 1
            
    db.session.commit()
    
    return jsonify({
        'success': True,
        'actualizados': actualizados,
        'omitidos_por_estado': omitidos,
        'no_encontrados': no_encontrados,
        'segundos': round(time.time() - t0, 2)
    })
