import os
import glob
import json
import time
import logging
import tempfile
import mimetypes
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import io
from datetime import datetime, timedelta
from collections import Counter
from PIL import Image, ImageOps

# Setup Flask application
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    db_path = os.path.join(BASE_DIR, "nucleus.db")
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nucleus_dev_key_change_me')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50 MB
app.config['EVIDENCIA_DIR'] = os.path.join(BASE_DIR, 'static', 'evidencia')
os.makedirs(app.config['EVIDENCIA_DIR'], exist_ok=True)
app.config['EVIDENCIA_MAX_LADO'] = int(os.environ.get('EVIDENCIA_MAX_LADO', 1280))
app.config['EVIDENCIA_CALIDAD'] = int(os.environ.get('EVIDENCIA_CALIDAD', 80))
# Backblaze B2 (opcional): si se configuran estas variables, las fotos se suben a B2.
app.config['B2_ENDPOINT_URL'] = os.environ.get('B2_ENDPOINT_URL', '')
app.config['B2_KEY_ID'] = os.environ.get('B2_KEY_ID', '')
app.config['B2_APP_KEY'] = os.environ.get('B2_APP_KEY', '')
app.config['B2_BUCKET'] = os.environ.get('B2_BUCKET', '')
app.config['B2_REGION'] = os.environ.get('B2_REGION', 'us-west-004')

db = SQLAlchemy(app)

# --- MODELS ---
class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), default='')
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), default='supervisor') # 'admin', 'supervisor', 'gestor'

class Proyecto(db.Model):
    __tablename__ = 'proyectos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.String(200))
    icono = db.Column(db.String(50), default='fa-folder-open', nullable=False)

class AppConfig(db.Model):
    __tablename__ = 'app_config'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    clave = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('proyecto_id', 'clave', name='_proj_clave_uc'),)

class NucleusData(db.Model):
    __tablename__ = 'nucleus_data'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    data_json = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('proyecto_id', 'key_value', name='_proj_key_uc'),)

class NucleusHistory(db.Model):
    __tablename__ = 'nucleus_history'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    data_json = db.Column(db.Text, nullable=False)
    fecha_consolidado = db.Column(db.DateTime, default=datetime.utcnow)

class FiltroMaestro(db.Model):
    __tablename__ = 'filtros_maestros'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    columna = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.UniqueConstraint('proyecto_id', 'columna', 'valor', name='_proj_filtro_uc'),)

class TablaMaestra(db.Model):
    __tablename__ = 'tablas_maestras'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    columna_criterio = db.Column(db.String(100), nullable=False)
    valor_criterio = db.Column(db.String(100), nullable=False)
    nueva_columna = db.Column(db.String(100), nullable=False)
    nuevo_valor = db.Column(db.String(100), nullable=False)

class ReglaEstadoManual(db.Model):
    __tablename__ = 'reglas_estado_manual'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    columna_criterio = db.Column(db.String(100), nullable=False)
    valor_criterio = db.Column(db.String(100), nullable=False)
    columna_manual = db.Column(db.String(100), nullable=False)
    nuevo_valor = db.Column(db.String(100), nullable=False)

class AccesoProyecto(db.Model):
    __tablename__ = 'accesos_proyecto'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    # restricciones: JSON string ej: {"JEFATURA": ["LIMA", "CALLAO"]}
    restricciones = db.Column(db.Text, default='{}') 
    __table_args__ = (db.UniqueConstraint('usuario_id', 'proyecto_id', name='_user_proj_uc'),)

class KpiConfig(db.Model):
    __tablename__ = 'kpi_configs'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    col_inicio = db.Column(db.String(100), nullable=False)
    restar_contra = db.Column(db.String(20), default='HOY') # 'HOY', 'COLUMNA'
    col_fin = db.Column(db.String(100), nullable=True)
    tipo = db.Column(db.String(20), default='DILACION')

class HistorialCambios(db.Model):
    __tablename__ = 'historial_cambios'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    username = db.Column(db.String(50), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    campo_modificado = db.Column(db.String(100), nullable=False)
    valor_anterior = db.Column(db.Text, nullable=True)
    valor_nuevo = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Tecnico(db.Model):
    __tablename__ = 'tecnicos'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    contrata = db.Column(db.String(120), default='')
    especialidad = db.Column(db.String(120), default='')
    telefono = db.Column(db.String(30), default='')

class Cotizacion(db.Model):
    __tablename__ = 'cotizaciones'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    numero = db.Column(db.String(50), nullable=False)
    nota = db.Column(db.Text, default='')
    cotizado_por = db.Column(db.String(100), default='')
    revisado_por = db.Column(db.String(100), default='')
    gastos_json = db.Column(db.Text, default='[]')
    mano_obra_json = db.Column(db.Text, default='[]')
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)
    bloqueada = db.Column(db.Boolean, default=True)
    formato = db.Column(db.String(20), default='')
    site = db.Column(db.String(200), default='')
    supervisor = db.Column(db.String(120), default='')
    items_json = db.Column(db.Text, default='[]')

# Auth Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- HELPERS ---
@app.route('/api/admin/column_values')
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

def inject_kpis(pid, rows):
    configs = KpiConfig.query.filter_by(proyecto_id=pid).all()
    if not configs: return rows, {}
    
    hoy = datetime.now()
    kpi_meta = {}
    
    # Pre-calculate rules
    for kpi in configs:
        if kpi.tipo == 'ACUMULADO':
            col_raw = kpi.col_inicio
            # ignore empty strings from splitting
            cols = [c.strip() for c in col_raw.split(',') if c.strip()]
            
            if not cols: continue

            # Handle multiple filters stored in col_fin as JSON
            filters = []
            try:
                if kpi.col_fin and (kpi.col_fin.startswith('[') or kpi.col_fin.startswith('{')):
                    filters = json.loads(kpi.col_fin)
                    if not isinstance(filters, list): filters = []
                elif kpi.restar_contra and kpi.restar_contra != 'HOY':
                    # Legacy single filter support
                    filters = [{"col": kpi.restar_contra, "val": kpi.col_fin}]
            except:
                filters = []

            combined_vals = []
            for r in rows:
                # Apply ALL filters (AND logic)
                matches_all = True
                for f in filters:
                    f_col = f.get('col')
                    f_val = f.get('val')
                    if f_col:
                        # rows are list of dicts, use r.get()
                        if str(r.get(f_col, '')).strip() != str(f_val).strip():
                            matches_all = False
                            break
                
                if matches_all:
                    vals = [str(r.get(c, '')).strip() for c in cols]
                    if all(vals):
                        combined_vals.append(" | ".join(vals))
            
            if combined_vals:
                counts = Counter(combined_vals)
                
                # --- NEW TOP 4 RANKING LOGIC ---
                sorted_keys = sorted(counts.keys(), key=lambda x: counts[x], reverse=True)
                ranks = {}
                for i, k in enumerate(sorted_keys[:4]):
                    ranks[k] = i + 1  # Rank 1, 2, 3, 4
                
                # Use KPI ID to avoid collisions
                kpi_meta[kpi.id] = {
                    'counts': dict(counts),
                    'ranks': ranks,
                    'max': max(counts.values()) if counts else 0,
                    'cols_involved': cols,
                    'filters': filters
                }
        elif kpi.tipo == 'RESALTADO':
            # Highlight rules: { "COLUMN": {"VALUE": "STYLE"} }
            if 'resaltadores' not in kpi_meta: kpi_meta['resaltadores'] = {}
            col = kpi.col_inicio
            val = kpi.col_fin # ITEM to highlight stored here
            if col not in kpi_meta['resaltadores']: kpi_meta['resaltadores'][col] = {}
            kpi_meta['resaltadores'][col][val] = 'hit' # Mark for highlighting

    for kpi in configs:
        if kpi.tipo != 'DILACION': continue
        
        for row in rows:
            val_inicio = row.get(kpi.col_inicio)
            if not val_inicio:
                row[f"KPI_{kpi.nombre}"] = None
                continue
                
            # Try to parse date using pandas for robustness
            try:
                # Use pandas to parse almost any common date format
                f_inicio = pd.to_datetime(str(val_inicio).strip())
                if pd.isna(f_inicio): f_inicio = None
            except:
                f_inicio = None
            
            if not f_inicio:
                row[f"KPI_{kpi.nombre}"] = None
                continue
                
            target_date = pd.to_datetime(hoy)
            if kpi.restar_contra == 'COLUMNA' and kpi.col_fin:
                val_fin = row.get(kpi.col_fin)
                if val_fin:
                    try:
                        f_fin = pd.to_datetime(str(val_fin).strip())
                        if not pd.isna(f_fin):
                            target_date = f_fin
                    except: pass
            
            diff = target_date - f_inicio
            row[f"KPI_{kpi.nombre}"] = max(0, diff.days)
            
    return rows, kpi_meta

def apply_data_restrictions(data_list, res_obj):
    """
    Applies role-based data filtering based on the res_obj.
    Does case-insensitive comparison and ignores missing columns.
    """
    if not res_obj:
        return data_list
        
    filtered = []
    
    # Pre-process restrictions to be robust (uppercase lists)
    parsed_res = {}
    for col, vals in res_obj.items():
        if not vals: continue
        # Ensure it's a list and uppercase all elements
        if isinstance(vals, list):
            parsed_res[col] = [str(v).strip().upper() for v in vals]
        else:
            parsed_res[col] = [str(vals).strip().upper()]
    
    # If after parsing it's empty, no restrictions apply
    if not parsed_res:
        return data_list
        
    for d in data_list:
        keep = True
        for col_name, allowed_vals in parsed_res.items():
            if col_name not in d: continue # Flexible filtering
            
            val_in_row = str(d.get(col_name, '')).strip().upper()
            if val_in_row not in allowed_vals:
                keep = False; break
        if keep:
            filtered.append(d)
            
    return filtered


def _parse_galones(n):
    """Convierte un valor de galones a float (acepta coma o punto)."""
    try:
        return float(str(n or '').replace(',', '.').strip())
    except (ValueError, TypeError):
        return 0.0


def _flm_wo_list():
    """Lista de WOs (CM) declarados en el proyecto FLM, para el buscador de Combustible."""
    try:
        flm_proy = Proyecto.query.filter_by(nombre='FLM').first()
        if not flm_proy:
            return []
        wo_set = set()
        wo_key = None
        for r in NucleusData.query.filter_by(proyecto_id=flm_proy.id).limit(5).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            for k in d.keys():
                if 'WO' in k.upper() and 'NUMBER' in k.upper() or 'Número de WO' in k or 'Numero de WO' in k:
                    wo_key = k
                    break
            if wo_key:
                break
        if wo_key:
            for r in NucleusData.query.filter_by(proyecto_id=flm_proy.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                wo = str(d.get(wo_key, '')).strip()
                if wo:
                    wo_set.add(wo)
        else:
            for r in NucleusData.query.filter_by(proyecto_id=flm_proy.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                for k, v in d.items():
                    if 'WO' in str(k).upper():
                        w = str(v).strip()
                        if w:
                            wo_set.add(w)
        return sorted(wo_set)
    except Exception:
        return []


def _combustible_saldo(pid, generador):
    """Saldo disponible (INGRESOS - GASTOS) actual de un generador en Combustible."""
    try:
        bal = 0.0
        for r in NucleusData.query.filter_by(proyecto_id=pid).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            if str(d.get('QR ASIGNADO', '')).strip() != generador:
                continue
            mov = str(d.get('MOVIMIENTO', '')).strip().upper()
            g = _parse_galones(d.get('GALONES'))
            bal = bal + g if mov != 'GASTO' else bal - g
        return bal
    except Exception:
        return 0.0


# --- DB INIT & MIGRATION ---
with app.app_context():
    is_sqlite = db.engine.dialect.name == 'sqlite'
    # Detect if we need to migrate or just create
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    # Check if _old tables already exist from a failed prior run
    has_old = 'nucleus_data_old' in tables
    
    # If it's the old schema (no project_id in nucleus_data)
    needs_migration = False
    if 'nucleus_data' in tables:
        cols = [c['name'] for c in inspector.get_columns('nucleus_data')]
        if 'proyecto_id' not in cols:
            needs_migration = True

    if is_sqlite and needs_migration and not has_old:
        print("Migrating database to Multi-Project schema...")
        # Simple migration: Rename old and copy
        db.session.execute(db.text("ALTER TABLE nucleus_data RENAME TO nucleus_data_old"))
        db.session.execute(db.text("ALTER TABLE app_config RENAME TO app_config_old"))
        db.session.execute(db.text("ALTER TABLE filtros_maestros RENAME TO filtros_maestros_old"))
        db.session.execute(db.text("ALTER TABLE tablas_maestras RENAME TO tablas_maestras_old"))
        db.session.commit()
        has_old = True # Now we have them

    db.create_all()

    # Migration: Add 'nombre' column to usuarios if missing (must run before any Usuario query)
    try:
        ucols = [c['name'] for c in inspect(db.engine).get_columns('usuarios')]
        if 'nombre' not in ucols:
            db.session.execute(db.text("ALTER TABLE usuarios ADD COLUMN nombre VARCHAR(100) DEFAULT ''"))
            db.session.commit()
            print("Added 'nombre' column to usuarios")
    except Exception as e:
        print("Warning: could not add nombre column:", e)
    
    # Create Default Admin if none
    if not Usuario.query.first():
        admin = Usuario(username='admin', password_hash=generate_password_hash('admin123'), rol='admin')
        db.session.add(admin)
        db.session.commit()

    # Migration: allow multiple cotizaciones per key_value (drop unique constraint)
    try:
        cot_tables = inspect(db.engine).get_table_names()
        if 'cotizaciones' in cot_tables:
            if is_sqlite:
                # SQLite: check the table DDL for the unique constraint (it's a CONSTRAINT, not an index)
                sql = db.session.execute(db.text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='cotizaciones'"
                )).scalar() or ''
                if '_proj_key_coti_uc' in sql:
                    db.session.execute(db.text("ALTER TABLE cotizaciones RENAME TO cotizaciones_old"))
                    db.session.commit()
                    db.create_all()
                    cols = [c['name'] for c in inspect(db.engine).get_columns('cotizaciones_old')]
                    collist = ', '.join(cols)
                    db.session.execute(db.text(
                        f"INSERT INTO cotizaciones ({collist}) SELECT {collist} FROM cotizaciones_old"
                    ))
                    db.session.execute(db.text("DROP TABLE cotizaciones_old"))
                    db.session.commit()
                    print("Cotizaciones: unique constraint removed (SQLite)")
            else:
                # Postgres: drop named constraint directly
                db.session.execute(db.text("ALTER TABLE cotizaciones DROP CONSTRAINT IF EXISTS _proj_key_coti_uc"))
                db.session.commit()
                print("Cotizaciones: unique constraint removed (Postgres)")
    except Exception as e:
        print("Warning: cotizaciones migration:", e)

    # Migration: cotizaciones formato Cobra (FLM): formato, site, supervisor, items_json
    try:
        if 'cotizaciones' in inspect(db.engine).get_table_names():
            cot_cols = [c['name'] for c in inspect(db.engine).get_columns('cotizaciones')]
            with db.engine.begin() as conn:
                if 'formato' not in cot_cols:
                    conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN formato VARCHAR(20) DEFAULT ''"))
                if 'site' not in cot_cols:
                    conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN site VARCHAR(200) DEFAULT ''"))
                if 'supervisor' not in cot_cols:
                    conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN supervisor VARCHAR(120) DEFAULT ''"))
                if 'items_json' not in cot_cols:
                    conn.execute(db.text("ALTER TABLE cotizaciones ADD COLUMN items_json TEXT DEFAULT '[]'"))
            print("Cotizaciones: columnas formato Cobra listas")
    except Exception as e:
        print("Warning: cotizaciones cobra migration:", e)

    # Create Default Project "Pangeaco" ONLY when the DB is completely empty (fresh install)
    if not Proyecto.query.first():
        pangeaco = Proyecto(nombre='Pangeaco', descripcion='Proyecto inicial migrado')
        db.session.add(pangeaco)
        db.session.commit()
    else:
        # Reuse an existing project as target for any legacy migration
        pangeaco = Proyecto.query.first()
        
    if is_sqlite and has_old:
        pid = pangeaco.id
        print("Restoring data from old tables...")
        # Move data from old tables
        try:
            db.session.execute(db.text(f"INSERT OR IGNORE INTO nucleus_data (proyecto_id, key_value, data_json) SELECT {pid}, key_value, data_json FROM nucleus_data_old"))
            db.session.execute(db.text(f"INSERT OR IGNORE INTO app_config (proyecto_id, clave, valor) SELECT {pid}, clave, valor FROM app_config_old"))
            db.session.execute(db.text(f"INSERT OR IGNORE INTO filtros_maestros (proyecto_id, columna, valor) SELECT {pid}, columna, valor FROM filtros_maestros_old"))
            db.session.execute(db.text(f"INSERT OR IGNORE INTO tablas_maestras (proyecto_id, columna_criterio, valor_criterio, nueva_columna, nuevo_valor) SELECT {pid}, columna_criterio, valor_criterio, nueva_columna, nuevo_valor FROM tablas_maestras_old"))
        except Exception as e:
            print(f"Error restoring data: {e}")
        
        # Cleanup
        db.session.execute(db.text("DROP TABLE IF EXISTS nucleus_data_old"))
        db.session.execute(db.text("DROP TABLE IF EXISTS app_config_old"))
        db.session.execute(db.text("DROP TABLE IF EXISTS filtros_maestros_old"))
        db.session.execute(db.text("DROP TABLE IF EXISTS tablas_maestras_old"))
        db.session.commit()

    # Migration: Rename editor -> supervisor
    try:
        db.session.execute(db.text("UPDATE usuarios SET rol = 'supervisor' WHERE rol = 'editor'"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Migration: Ensure fixed projects FLM, PEXT, Dataper, Material exist
    fixed = [('FLM', 'Fiscalización Lima Metropolitana'), ('PEXT', 'Proyecto Externo'), ('Dataper', 'DataPer S.A.C.'),
             ('Material', 'Materiales Disponibles'), ('Site Name', 'Sitios (solo FLM)'), ('Generadores', 'Grupos Electrógenos (solo FLM)'),
             ('Combustible', 'Consumo de Combustible (solo FLM)'), ('Cotizaciones', 'Registro de Cotizaciones (solo FLM)'),
             ('SITE', 'Maestro de Sites – Libro1 (39 columnas)')]
    for nombre, desc in fixed:
        if not Proyecto.query.filter_by(nombre=nombre).first():
            db.session.add(Proyecto(nombre=nombre, descripcion=desc))
    db.session.commit()

    # Migration: Configure Dataper columns (TECNICO, DOCUMENTO, CONTRATA, CELULAR, SUPERVISOR, DEPARTAMENTO, PROYECTO + ACTIVO/CESADO)
    dataper = Proyecto.query.filter_by(nombre='Dataper').first()
    if dataper:
        dataper_cols = [
            {'nombre': 'TECNICO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DOCUMENTO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CONTRATA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CELULAR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUPERVISOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DEPARTAMENTO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'PROYECTO', 'tipo': 'lista', 'opciones': ['FLM', 'PEXT']},
            {'nombre': 'ESTADO', 'tipo': 'lista', 'opciones': ['ACTIVO', 'CESADO']}
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=dataper.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(dataper_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=dataper.id, clave='manual_columns', valor=json.dumps(dataper_cols, ensure_ascii=False)))

        pk_cfg = AppConfig.query.filter_by(proyecto_id=dataper.id, clave='primary_key').first()
        if not pk_cfg:
            db.session.add(AppConfig(proyecto_id=dataper.id, clave='primary_key', valor='DOCUMENTO'))

        schema_cfg = AppConfig.query.filter_by(proyecto_id=dataper.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=dataper.id, clave='app_schema', valor=json.dumps([])))
        db.session.commit()

    # Migration: Configure Material columns (COD_MATERIAL, DESCRIPCION_MATERIAL, PROYECTO, UM, TIPO)
    material_proy = Proyecto.query.filter_by(nombre='Material').first()
    if material_proy:
        material_proy.icono = 'fa-boxes-stacked'
        material_cols = [
            {'nombre': 'COD_MATERIAL', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DESCRIPCION_MATERIAL', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'PROYECTO', 'tipo': 'lista', 'opciones': ['FLM', 'PEXT']},
            {'nombre': 'UM', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'TIPO', 'tipo': 'texto', 'opciones': []}
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=material_proy.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(material_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=material_proy.id, clave='manual_columns', valor=json.dumps(material_cols, ensure_ascii=False)))

        pk_cfg = AppConfig.query.filter_by(proyecto_id=material_proy.id, clave='primary_key').first()
        if pk_cfg:
            pk_cfg.valor = 'COD_MATERIAL'
        else:
            db.session.add(AppConfig(proyecto_id=material_proy.id, clave='primary_key', valor='COD_MATERIAL'))

        schema_cfg = AppConfig.query.filter_by(proyecto_id=material_proy.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=material_proy.id, clave='app_schema', valor=json.dumps([])))
        db.session.commit()

    # Migration: Configure Site Name columns (NOMBRE DE SITE, DIRECCION, LATITUD, LONGITUD, ESTADO)
    site_proy = Proyecto.query.filter_by(nombre='Site Name').first()
    if site_proy:
        site_cols = [
            {'nombre': 'NOMBRE DE SITE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'DIRECCION', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'LATITUD', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'LONGITUD', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'ESTADO', 'tipo': 'lista', 'opciones': ['ACTIVO', 'INACTIVO']}
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(site_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='manual_columns', valor=json.dumps(site_cols, ensure_ascii=False)))

        pk_cfg = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='primary_key').first()
        if not pk_cfg:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='primary_key', valor='NOMBRE DE SITE'))

        schema_cfg = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='app_schema', valor=json.dumps([])))
        db.session.commit()

    # Migration: Configure Generadores columns (SERIE DE EQUIPO, TIPO, TECNICO ASIGNADO, ZONA, QR ASIGNADO)
    gen_proy = Proyecto.query.filter_by(nombre='Generadores').first()
    if gen_proy:
        gen_proy.icono = 'fa-bolt'
        gen_cols = [
            {'nombre': 'QR ASIGNADO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SERIE DE EQUIPO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'TIPO', 'tipo': 'lista', 'opciones': ['PROPIO', 'ALQUILADO', 'ENTEL']},
            {'nombre': 'TIPO DE COMBUSTIBLE', 'tipo': 'lista', 'opciones': ['GASOLINA', 'PETROLEO', 'DIESEL']},
            {'nombre': 'TECNICO ASIGNADO', 'tipo': 'lista', 'opciones': []},
            {'nombre': 'ZONA', 'tipo': 'texto', 'opciones': []}
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=gen_proy.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(gen_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=gen_proy.id, clave='manual_columns', valor=json.dumps(gen_cols, ensure_ascii=False)))

        # QR ASIGNADO es la llave del negocio (el usuario la llena). La llave interna
        # pasa a ser auto-generada para permitir QR vacíos mientras se van asignando.
        pk_cfg = AppConfig.query.filter_by(proyecto_id=gen_proy.id, clave='primary_key').first()
        if pk_cfg:
            db.session.delete(pk_cfg)

        schema_cfg = AppConfig.query.filter_by(proyecto_id=gen_proy.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=gen_proy.id, clave='app_schema', valor=json.dumps([])))
        db.session.commit()

    # Migration: Seed Generadores con los equipos declarados (SERIE DE EQUIPO).
    # Solo inserta las series que aún no existan (idempotente).
    gen_proy = Proyecto.query.filter_by(nombre='Generadores').first()
    if gen_proy:
        series = ['06-0002-3145', '06-002-3141', '06-0002-3196', '06-0002-3184',
                  '06-0002-3140', '06-0002-3132', '06-0002-3108', '06-0002-3207',
                  '06-0002-3139', '06-0002-3123', '06-0002-3115', '06-0002-3117',
                  '06-0002-3226', '06-0002-3210', '06-0002-3182', '06-0002-3174',
                  '06-0002-3154', '06-0002-3126', '06-0002-3106', '06-0002-3102',
                  '06-0002-3118', '06-0002-3213', '06-0002-3193', '06-0002-3129',
                  '06-0002-3179', '06-0002-3114']
        existing_keys = {r.key_value for r in NucleusData.query.filter_by(proyecto_id=gen_proy.id).all()}
        for s in series:
            if s not in existing_keys:
                db.session.add(NucleusData(proyecto_id=gen_proy.id, key_value=s,
                                           data_json=json.dumps({'SERIE DE EQUIPO': s}, ensure_ascii=False)))
        # Asegurar que los registros existentes tengan los nuevos campos (QR ASIGNADO vacío
        # para que el usuario lo llene, ZONA y TECNICO ASIGNADO inicialmente vacíos).
        for r in NucleusData.query.filter_by(proyecto_id=gen_proy.id).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            changed = False
            if 'QR ASIGNADO' not in d:
                d['QR ASIGNADO'] = ''
                changed = True
            if 'ZONA' not in d:
                d['ZONA'] = ''
                changed = True
            if 'TECNICO ASIGNADO' not in d:
                d['TECNICO ASIGNADO'] = ''
                changed = True
            if 'TIPO DE COMBUSTIBLE' not in d:
                d['TIPO DE COMBUSTIBLE'] = ''
                changed = True
            if changed:
                r.data_json = json.dumps(d, ensure_ascii=False)
        db.session.commit()

    # Migration: Configure Combustible columns (QR ASIGNADO, TIPO, TECNICO ASIGNADO)
    comb_proy = Proyecto.query.filter_by(nombre='Combustible').first()
    if comb_proy:
        comb_proy.icono = 'fa-gas-pump'
        comb_cols = [
            {'nombre': 'FECHA', 'tipo': 'fecha', 'opciones': []},
            {'nombre': 'QR ASIGNADO', 'tipo': 'lista', 'opciones': []},
            {'nombre': 'TIPO', 'tipo': 'lista', 'opciones': ['PROPIO', 'ALQUILADO', 'ENTEL']},
            {'nombre': 'TECNICO ASIGNADO', 'tipo': 'lista', 'opciones': []},
            {'nombre': 'ZONA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'NOMBRE DE SITE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'MOVIMIENTO', 'tipo': 'lista', 'opciones': ['INGRESO', 'GASTO']},
            {'nombre': 'NUMERO FACTURA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GALONES', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'FOTO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'WO NUMBER', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'ID DE REPORTE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GESTOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'COMENTARIOS', 'tipo': 'texto', 'opciones': []}
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=comb_proy.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(comb_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=comb_proy.id, clave='manual_columns', valor=json.dumps(comb_cols, ensure_ascii=False)))

        pk_cfg = AppConfig.query.filter_by(proyecto_id=comb_proy.id, clave='primary_key').first()
        if pk_cfg:
            db.session.delete(pk_cfg)

        schema_cfg = AppConfig.query.filter_by(proyecto_id=comb_proy.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=comb_proy.id, clave='app_schema', valor=json.dumps([])))

        # Asegurar que los registros existentes tengan el nuevo campo ID DE REPORTE (vacío).
        for r in NucleusData.query.filter_by(proyecto_id=comb_proy.id).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            if 'ID DE REPORTE' not in d:
                d['ID DE REPORTE'] = ''
                r.data_json = json.dumps(d, ensure_ascii=False)
        db.session.commit()

    # Migration: Configure Cotizaciones columns (registro de cotizaciones FLM,
    # mismo esquema del formato Cobra + campos de control NUMERO WO y NOMBRE SITE).
    cot_proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if cot_proy:
        cot_proy.icono = 'fa-file-invoice-dollar'
        cot_cols = [
            {'nombre': 'FECHA', 'tipo': 'fecha', 'opciones': []},
            {'nombre': 'N° COTIZACION', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'TICKET', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'NUMERO WO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'NOMBRE SITE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SITE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUPERVISOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'OBJETIVO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUB TOTAL + FEE', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GESTOR', 'tipo': 'texto', 'opciones': []}
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(cot_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='manual_columns', valor=json.dumps(cot_cols, ensure_ascii=False)))

        # La llave del negocio es el N° de cotización completo (HW-AAAA-XXXXXXX).
        pk_cfg = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='primary_key').first()
        if pk_cfg:
            pk_cfg.valor = 'N° COTIZACION'
        else:
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='primary_key', valor='N° COTIZACION'))

        # Re-key: registros creados antes con llave auto-numérica pasan a usar su N°.
        for r in NucleusData.query.filter_by(proyecto_id=cot_proy.id).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            num = str(d.get('N° COTIZACION', '') or '').strip()
            if num and r.key_value != num:
                dup = NucleusData.query.filter_by(proyecto_id=cot_proy.id, key_value=num).first()
                if not dup:
                    r.key_value = num

        schema_cfg = AppConfig.query.filter_by(proyecto_id=cot_proy.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=cot_proy.id, clave='app_schema', valor=json.dumps([])))
        db.session.commit()

    # Migration: Configure SITE columns (maestro Libro1 – 39 columnas)
    site_proy = Proyecto.query.filter_by(nombre='SITE').first()
    if site_proy:
        site_proy.icono = 'fa-location-dot'
        site_cols = [
            {'nombre': 'Código Site', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Nombre Site', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Estado', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Prioridad', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Departamento', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Provincia', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Distrito', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Dirección', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Latitud (°)', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Longitud (°)', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Región', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Coordinador O&M Sitios', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Tipo de Torre', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Altura de Torre (m)', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Tipo de Estación', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Cobicador', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Infraestructura Critica', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Tipo de Site', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Sede', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Week', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'Oficinas FM', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CITY', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'REGION HW', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUBCON', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'TEAMS', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SUPERVISOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'BASE SUPERVISOR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CELULAR', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CORREO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'REGIONAL MANAGER HUAWEI', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CEL RM', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CORREO RM', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GRUPOS ELECTROGENOS (60)', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'GRUPOS ELECTROGENOS ENTEL', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'AVR  % CORTES', 'tipo': 'texto', 'opciones': []},
            {'nombre': '4X4', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'MINIVAN', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'MOTO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'MOTOCARGA', 'tipo': 'texto', 'opciones': []},
        ]
        mc_cfg = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='manual_columns').first()
        if mc_cfg:
            mc_cfg.valor = json.dumps(site_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='manual_columns', valor=json.dumps(site_cols, ensure_ascii=False)))
        # La llave del maestro es el Código Site (también se usa como campo "site")
        pk_cfg = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='primary_key').first()
        if pk_cfg:
            pk_cfg.valor = 'Código Site'
        else:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='primary_key', valor='Código Site'))
        schema_cfg = AppConfig.query.filter_by(proyecto_id=site_proy.id, clave='app_schema').first()
        if not schema_cfg:
            db.session.add(AppConfig(proyecto_id=site_proy.id, clave='app_schema', valor=json.dumps([])))
        db.session.commit()

    # Migration: "Fault Level" es dato de origen (inmutable) -> no debe ser columna manual editable.
    # Se elimina de la configuracion para que nadie pueda editarla (ni admin).
    pext = Proyecto.query.filter_by(nombre='PEXT').first()
    if pext:
        mc_cfg = AppConfig.query.filter_by(proyecto_id=pext.id, clave='manual_columns').first()
        if mc_cfg:
            try:
                existing_cols = json.loads(mc_cfg.valor)
                if not isinstance(existing_cols, list): existing_cols = []
            except Exception:
                existing_cols = []
            # Remove the separate hours column (now shown inside Fault Level badge)
            # and Fault Level itself (source data, must not be editable)
            existing_cols = [c for c in existing_cols if c.get('nombre') not in ('Hrs Respuesta', 'Fault Level')]
            mc_cfg.valor = json.dumps(existing_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=pext.id, clave='manual_columns', valor=json.dumps([], ensure_ascii=False)))

        fault_rules = [
            ('Critical', '8hrs'),
            ('Alta', '10hrs'),
            ('Media', '48hrs'),
            ('Baja', '72hrs')
        ]
        for nivel, hrs in fault_rules:
            exists = TablaMaestra.query.filter_by(proyecto_id=pext.id, columna_criterio='Fault Level',
                                                  valor_criterio=nivel, nueva_columna='Hrs Respuesta').first()
            if exists:
                exists.nuevo_valor = hrs
            else:
                db.session.add(TablaMaestra(proyecto_id=pext.id, columna_criterio='Fault Level',
                                            valor_criterio=nivel, nueva_columna='Hrs Respuesta', nuevo_valor=hrs))
        db.session.commit()

    # Migration: Seed SERVICIO options for WO detail (PEXT & FLM)
    default_servicios = ['PREVENTIVO', 'CORRECTIVO', 'PREDICTIVO', 'ABASTECIMIENTO DE COMBUSTIBLE',
                         'ADICIONALES', 'CORTE PROGRAMADO', 'TRABAJO PROGRAMADO']
    for proy_nombre in ('PEXT', 'FLM'):
        sp = Proyecto.query.filter_by(nombre=proy_nombre).first()
        if sp:
            scfg = AppConfig.query.filter_by(proyecto_id=sp.id, clave='servicio_opciones').first()
            if not scfg:
                db.session.add(AppConfig(proyecto_id=sp.id, clave='servicio_opciones',
                                         valor=json.dumps(default_servicios, ensure_ascii=False)))
    db.session.commit()

    # Migration: Asegurar columnas de detalle para FLM (campos que llena el gestor en el modal WO).
    # Si falta alguna, se agrega a manual_columns para que aparezcan en la tabla y en el botón Columnas.
    flm_proy = Proyecto.query.filter_by(nombre='FLM').first()
    if flm_proy:
        flm_cfg = AppConfig.query.filter_by(proyecto_id=flm_proy.id, clave='manual_columns').first()
        try:
            flm_cols = json.loads(flm_cfg.valor) if flm_cfg else []
            if not isinstance(flm_cols, list):
                flm_cols = []
        except Exception:
            flm_cols = []
        flm_names = {str(c.get('nombre', '')).strip() for c in flm_cols if isinstance(c, dict)}
        flm_detalle_cols = [
            {'nombre': 'SERVICIO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CIUDAD', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'TECNICO ASIGNADO', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CONTRATA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'MOTIVO DE AVERÍA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SOLUCIÓN', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'LATITUD', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'LONGITUD', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'SE INSTALÓ MUFAS', 'tipo': 'lista', 'opciones': ['Sí', 'No']},
            {'nombre': 'LATITUD MUFAS', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'LONGITUD MUFAS', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'INICIO DE PARADA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'FIN DE PARADA', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'REQUIERE CORRECTIVO FINAL', 'tipo': 'lista', 'opciones': ['Sí', 'No']}
        ]
        for col in flm_detalle_cols:
            if col['nombre'] not in flm_names:
                flm_cols.append(col)
                flm_names.add(col['nombre'])
        if flm_cfg:
            flm_cfg.valor = json.dumps(flm_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=flm_proy.id, clave='manual_columns', valor=json.dumps(flm_cols, ensure_ascii=False)))
        db.session.commit()

    # Migration: Campos del checklist de PEXT (datos del gestor al atender la incidencia)
    pext_checklist = Proyecto.query.filter_by(nombre='PEXT').first()
    if pext_checklist:
        mc_cfg = AppConfig.query.filter_by(proyecto_id=pext_checklist.id, clave='manual_columns').first()
        try:
            existing_cols = json.loads(mc_cfg.valor) if mc_cfg else []
            if not isinstance(existing_cols, list):
                existing_cols = []
        except Exception:
            existing_cols = []
        existing_names = {str(c.get('nombre', '')).strip() for c in existing_cols if isinstance(c, dict)}
        pext_new_cols = [
            {'nombre': 'MOTIVO PARADA RELOJ', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'ROBO HURTO', 'tipo': 'lista', 'opciones': ['Sí', 'No']},
            {'nombre': 'SUPERVISOR ATENCIÓN', 'tipo': 'texto', 'opciones': []},
            {'nombre': 'CORREO CIERRE', 'tipo': 'lista', 'opciones': ['Sí', 'No']},
            {'nombre': 'MOTIVO NO ATENDIDO', 'tipo': 'texto', 'opciones': []}
        ]
        for col in pext_new_cols:
            if col['nombre'] not in existing_names:
                existing_cols.append(col)
                existing_names.add(col['nombre'])
        if mc_cfg:
            mc_cfg.valor = json.dumps(existing_cols, ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=pext_checklist.id, clave='manual_columns',
                                     valor=json.dumps(existing_cols, ensure_ascii=False)))
        db.session.commit()

    # --- Backfill: historial de estado inicial para registros históricos ---
    # Los registros importados antes de existir el seguimiento de cambios de estado
    # no tienen fila en historial_cambios. Se crea una entrada 'IMPORT' con el estado
    # actual para que el historial/estado de cada WO sea visible y no se pierda info.
    # Es idempotente: se ejecuta una sola vez por proyecto (flag en app_config).
    WO_STATE_COL_BF = 'Estado de la tarea (WO State)'
    STATE_TS_COL_BF = 'FECHA CAMBIO ESTADO'
    for proy in Proyecto.query.all():
        bf_cfg = AppConfig.query.filter_by(proyecto_id=proy.id, clave='historial_backfill_done').first()
        if bf_cfg:
            continue
        hist_keys = set(kv for (kv,) in db.session.query(HistorialCambios.key_value).filter(
            HistorialCambios.proyecto_id == proy.id,
            HistorialCambios.campo_modificado == WO_STATE_COL_BF).distinct().all())
        n = 0
        for r in NucleusData.query.filter_by(proyecto_id=proy.id).all():
            if r.key_value in hist_keys:
                continue
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            st = str(d.get(WO_STATE_COL_BF, '')).strip()
            if not st:
                continue
            fecha = datetime.utcnow()
            fec_txt = str(d.get(STATE_TS_COL_BF, '')).strip()
            if fec_txt:
                try:
                    fecha = datetime.strptime(fec_txt[:19], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            db.session.add(HistorialCambios(
                proyecto_id=proy.id, usuario_id=None, username='IMPORT',
                key_value=r.key_value, campo_modificado=WO_STATE_COL_BF,
                valor_anterior='', valor_nuevo=st, fecha=fecha))
            n += 1
        if n:
            print(f"Backfill historial de estado: {n} registros (proyecto {proy.nombre})")
        db.session.add(AppConfig(proyecto_id=proy.id, clave='historial_backfill_done', valor='1'))
        db.session.commit()

def safe_json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)

# --- AUTH & PROJECT ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['rol'] = str(user.rol).strip().lower()
            
            # Default to first project with access if none active
            if 'current_proyecto_id' not in session:
                if user.rol in ['admin', 'demo']:
                    proj = Proyecto.query.first()
                else:
                    acceso = AccesoProyecto.query.filter_by(usuario_id=user.id).first()
                    proj = db.session.get(Proyecto, acceso.proyecto_id) if acceso else None
                
                if proj:
                    session['current_proyecto_id'] = int(proj.id)
                    session['current_proyecto_nombre'] = proj.nombre
                    
            return redirect(url_for('index'))
        return render_template('login.html', error="Credenciales inválidas")
    return render_template('login.html')

def get_session_info():
    uid = session.get('user_id')
    rol = str(session.get('rol') or 'supervisor').strip().lower()
    pid_raw = session.get('current_proyecto_id')
    pid = int(pid_raw) if pid_raw else None
    return uid, rol, pid


def get_menu_proyectos(user_id, user_rol):
    """Proyectos que se muestran en el menú lateral.
    - admin/demo: todos.
    - resto: sus accesos + Dataper/Material si tiene FLM o PEXT asignado."""
    is_privileged = user_rol in ('admin', 'demo')
    if is_privileged:
        return Proyecto.query.order_by(Proyecto.id).all()
    accesos = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
    pids = [a.proyecto_id for a in accesos]
    proyectos = Proyecto.query.filter(Proyecto.id.in_(pids)).order_by(Proyecto.id).all()
    nombres = {p.nombre for p in proyectos}
    if 'FLM' in nombres or 'PEXT' in nombres:
        extra = Proyecto.query.filter(Proyecto.nombre.in_(['Dataper', 'Material'])).all()
        extra_ids = {e.id for e in proyectos}
        proyectos = proyectos + [e for e in extra if e.id not in extra_ids]
    if 'FLM' in nombres:
        site = Proyecto.query.filter_by(nombre='Site Name').first()
        if site and site.id not in {e.id for e in proyectos}:
            proyectos = proyectos + [site]
        gen = Proyecto.query.filter_by(nombre='Generadores').first()
        if gen and gen.id not in {e.id for e in proyectos}:
            proyectos = proyectos + [gen]
        comb = Proyecto.query.filter_by(nombre='Combustible').first()
        if comb and comb.id not in {e.id for e in proyectos}:
            proyectos = proyectos + [comb]
        cotp = Proyecto.query.filter_by(nombre='Cotizaciones').first()
        if cotp and cotp.id not in {e.id for e in proyectos}:
            proyectos = proyectos + [cotp]
        site2 = Proyecto.query.filter_by(nombre='SITE').first()
        if site2 and site2.id not in {e.id for e in proyectos}:
            proyectos = proyectos + [site2]
    return proyectos

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/switch_project/<int:pid>')
@login_required
def switch_project(pid):
    # Check permission
    if session.get('rol') not in ['admin', 'demo']:
        acceso = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id'), proyecto_id=pid).first()
        if not acceso:
            # Dataper/Material: permitir si el usuario tiene FLM o PEXT asignado.
            # Site Name: permitir solo si el usuario tiene FLM asignado.
            proy = db.session.get(Proyecto, pid)
            if proy and proy.nombre in ('Dataper', 'Material'):
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'PEXT'):
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('index'))
            elif proy and proy.nombre == 'Site Name':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('index'))
            elif proy and proy.nombre == 'Generadores':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('index'))
            elif proy and proy.nombre == 'Combustible':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('index'))
            elif proy and proy.nombre == 'Cotizaciones':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('index'))
            elif proy and proy.nombre == 'SITE':
                accs = AccesoProyecto.query.filter_by(usuario_id=session.get('user_id')).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre == 'FLM':
                        allowed = True
                        break
                if not allowed:
                    return redirect(url_for('index'))
            else:
                return redirect(url_for('index'))
            
    proj = db.session.get(Proyecto, pid)
    proj = db.session.get(Proyecto, pid)
    if proj:
        session['current_proyecto_id'] = int(proj.id)
        session['current_proyecto_nombre'] = proj.nombre
    
    # Redirect back to specified page, referrer, or index
    target = request.args.get('next') or request.referrer or url_for('index')
    return redirect(target)

# --- MAIN ROUTES ---
@app.route('/')
@login_required
def index():
    user_id, user_rol, pid = get_session_info()
    is_admin = user_rol == 'admin'
    is_privileged = user_rol in ['admin', 'demo']

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
    # activos de Dataper con PROYECTO=FLM (catálogo declarado por el admin).
    # Combustible: QR ASIGNADO lista los QR declarados en Generadores, TIPO se
    # autocompleta desde el mapa generador->TIPO, TECNICO ASIGNADO lista los técnicos FLM.
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
                if pr and pr != 'FLM':
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
    
    # Load and Filter data
    rows = NucleusData.query.filter_by(proyecto_id=pid).limit(2000).all()
    raw_data = []
    for r in rows:
        d = json.loads(r.data_json)
        d['_key'] = r.key_value
        raw_data.append(d)

    # Dataper y Material: solo mostrar registros cuyo campo PROYECTO sea FLM o PEXT
    # según los proyectos asignados al usuario (si tiene ambos, muestra ambos).
    if proy_actual_nombre in ('Dataper', 'Material'):
        if is_privileged:
            allowed_proy = {'FLM', 'PEXT'}
        else:
            accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
            allowed_proy = set()
            for a in accs:
                ap = db.session.get(Proyecto, a.proyecto_id)
                if ap and ap.nombre in ('FLM', 'PEXT'):
                    allowed_proy.add(ap.nombre)
        raw_data = [d for d in raw_data if str(d.get('PROYECTO', '')).strip() in allowed_proy]

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
            ordered = sorted(data, key=lambda d: (str(d.get('FECHA', '') or ''), str(d.get('_key', '') or '')))
            balance = {}
            for d in ordered:
                gen = str(d.get('QR ASIGNADO', '')).strip()
                mov = str(d.get('MOVIMIENTO', '')).strip().upper()
                g = _parse_gal(d.get('GALONES'))
                bal = balance.get(gen, 0.0)
                bal = bal + g if mov != 'GASTO' else bal - g
                balance[gen] = bal
                d['SALDO DISPONIBLE'] = round(bal, 2)
            gen_saldo_map = balance
            columns_set.add('SALDO DISPONIBLE')
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

@app.route('/dashboard')
@login_required
def dashboard():
    user_id, user_rol, pid = get_session_info()
    is_admin = user_rol == 'admin'

    if not pid:
        return redirect(url_for('index'))

    # Verify access to current project
    res_obj = {}
    is_privileged = user_rol in ['admin', 'demo']

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
    if proy_actual_nombre in ('Dataper', 'Material'):
        if is_privileged:
            allowed_proy = {'FLM', 'PEXT'}
        else:
            accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
            allowed_proy = set()
            for a in accs:
                ap = db.session.get(Proyecto, a.proyecto_id)
                if ap and ap.nombre in ('FLM', 'PEXT'):
                    allowed_proy.add(ap.nombre)
        raw_data = [d for d in raw_data if str(d.get('PROYECTO', '')).strip() in allowed_proy]
        
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

@app.route('/configuraciones')
@login_required
def configuraciones():
    user_rol = str(session.get('rol') or 'supervisor').strip().lower()
    if user_rol == 'gestor':
        return redirect(url_for('index'))
    user_id = session.get('user_id')
    if user_rol == 'admin':
        proyectos = Proyecto.query.all()
    else:
        accesos = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
        pids = [a.proyecto_id for a in accesos]
        proyectos = Proyecto.query.filter(Proyecto.id.in_(pids)).all()
    return render_template('configuraciones.html', proyectos_list=proyectos)

@app.route('/admin')
@login_required
def admin_panel():
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))
    return redirect(url_for('proyectos_page'))

@app.route('/proyectos')
@login_required
def proyectos_page():
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))
    proy = Proyecto.query.order_by(Proyecto.id).all()
    return render_template('proyectos.html', proyectos=proy, proyectos_list=proy)

@app.route('/usuarios')
@login_required
def usuarios_page():
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))
    proy = Proyecto.query.order_by(Proyecto.id).all()
    user = Usuario.query.all()
    accesos = {}
    for a in AccesoProyecto.query.all():
        accesos.setdefault(a.usuario_id, []).append(a.proyecto_id)
    return render_template('usuarios.html', proyectos=proy, usuarios=user, proyectos_list=proy, accesos=accesos)

# --- API ---
@app.route('/api/admin/proyecto', methods=['POST', 'DELETE'])
@login_required
def api_admin_proyecto():
    if session.get('rol') not in ['admin', 'demo']:
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
        if p and p.nombre in ('FLM', 'PEXT', 'Dataper', 'Material'):
            return jsonify({'error': 'Los proyectos FLM, PEXT, Dataper y Material no se pueden eliminar.'}), 403
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

@app.route('/api/tecnicos', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_tecnicos():
    if session.get('rol') != 'admin':
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

@app.route('/api/admin/usuario', methods=['POST', 'PUT', 'DELETE'])
@login_required
def api_admin_usuario():
    if session.get('rol') not in ['admin', 'demo']:
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
        try:
            u = db.session.get(Usuario, uid)
            if not u: return jsonify({'error': 'Usuario no encontrado'}), 404
            
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
        uid = request.json.get('id')
        if not uid: return jsonify({'error': 'ID requerido'}), 400
        if int(uid) == session.get('user_id'):
            return jsonify({'error': 'No puedes borrar tu propio usuario'}), 400
        try:
            u = db.session.get(Usuario, uid)
            if u:
                # Delete permissions too
                AccesoProyecto.query.filter_by(usuario_id=uid).delete()
                db.session.delete(u)
                db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/admin/usuario/duplicar', methods=['POST'])
@login_required
def api_admin_usuario_duplicar():
    if session.get('rol') not in ['admin']:
        return jsonify({'error': 'Solo admin puede duplicar usuarios.'}), 403
        
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

@app.route('/api/admin/permisos', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_admin_permisos():
    if session.get('rol') not in ['admin', 'demo']:
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

@app.route('/api/admin/columnas')
@login_required
def api_admin_columnas():
    if session.get('rol') not in ['admin', 'demo']:
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

@app.route('/api/import/manual_template')
@login_required
def api_import_manual_template():
    """Generates and downloads an Excel template with primary key + manual columns."""
    from flask import make_response
    pid = session.get('current_proyecto_id')
    if not pid:
        return jsonify({'error': 'No project selected'}), 400

    # Get the primary key column name
    config_key = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
    pk_name = config_key.valor if config_key else '_key'

    # Get manual columns
    manual_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    manual_cols = [mc['nombre'] for mc in json.loads(manual_cfg.valor)] if manual_cfg else []

    if not manual_cols:
        return jsonify({'error': 'No hay columnas manuales configuradas en este proyecto.'}), 400

    # Fetch all existing primary key values
    rows = NucleusData.query.filter_by(proyecto_id=pid).all()

    proy = db.session.get(Proyecto, pid)
    proy_nombre = proy.nombre if proy else ''

    # Plantilla del checklist de PEXT: PK + columnas que cubren el checklist.
    # Las columnas importadas (que ya tienen dato) van con su valor actual;
    # las manuales van vacías para que el gestor las llene.
    PEXT_CHECKLIST = [
        'Causa raíz',
        'Nombre de Site',
        'Estado del TT',
        'Fecha de creación (WO Creation date)',
        'Fecha y hora de WO a estado close',
        'Fault Level',
    ]
    PEXT_CHECKLIST_MANUAL = {
        'MATERIAL USADO', 'INICIO DE PARADA', 'FIN DE PARADA',
        'REQUIERE CORRECTIVO FINAL', 'SOLUCIÓN',
        'MOTIVO PARADA RELOJ', 'ROBO HURTO', 'SUPERVISOR ATENCIÓN',
        'CORREO CIERRE', 'MOTIVO NO ATENDIDO'
    }
    if proy_nombre == 'PEXT':
        checklist_cols = PEXT_CHECKLIST + [c for c in manual_cols if c in PEXT_CHECKLIST_MANUAL]
        data = {}
        for r in rows:
            d = json.loads(r.data_json)
            line = {pk_name: r.key_value}
            for col in PEXT_CHECKLIST:
                line[col] = str(d.get(col, '') or '')
            for col in checklist_cols:
                if col not in PEXT_CHECKLIST:
                    line[col] = ''
            data[r.key_value] = line
        if data:
            df = pd.DataFrame(list(data.values()))
        else:
            df = pd.DataFrame(columns=[pk_name] + checklist_cols)
        # Auto-adjust column widths
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Plantilla')
            ws = writer.sheets['Plantilla']
            for col_cells in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 45)
        output.seek(0)
        response = make_response(output.read())
        response.headers['Content-Disposition'] = 'attachment; filename=plantilla_checklist_PEXT.xlsx'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response

    # Build DataFrame: pk column pre-filled, manual columns empty
    df_data = {pk_name: [r.key_value for r in rows]}
    for col in manual_cols:
        df_data[col] = [''] * len(rows)
    df = pd.DataFrame(df_data)

    # Write to in-memory Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantilla')
        # Auto-adjust column widths
        ws = writer.sheets['Plantilla']
        for col_cells in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 40)
    output.seek(0)

    response = make_response(output.read())
    response.headers['Content-Disposition'] = 'attachment; filename=plantilla_columnas_manuales.xlsx'
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return response

@app.route('/api/import/preview', methods=['POST'])
@login_required
def api_import_preview():
    file = request.files.get('file')
    if not file: return jsonify({'error': 'No file'}), 400
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, encoding='utf-8', nrows=5, dtype=str)
        else:
            df = pd.read_excel(file, nrows=5, dtype=str)
        return jsonify({'columns': [str(c).strip() for c in df.columns]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import/process', methods=['POST'])
@login_required
def api_import_process():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para realizar importaciones.'}), 403
    import_type = request.form.get('type') or 'base' # 'base' or 'cruce'
    sum_duplicates = request.form.get('sum_duplicates') == 'true'
    sum_type = request.form.get('sum_type', 'number')
    consolidate_date = request.form.get('consolidate_date') == 'true'
    date_column = request.form.get('date_column', '').strip()
    cols_to_keep_str = request.form.get('columns_to_keep', '[]')
    columns_to_keep = json.loads(cols_to_keep_str)
    file_key = request.form.get('file_key', '').strip()

    # Columnas manuales del proyecto (datos editados por gestores)
    manual_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    manual_columns_list = []
    if manual_cfg:
        for mc in json.loads(manual_cfg.valor):
            if isinstance(mc, dict):
                manual_columns_list.append(str(mc.get('nombre', '')).strip())
    manual_columns_list = [c for c in manual_columns_list if c]
    
    file = request.files.get('file')
    if not file: return jsonify({'error': 'No file'}), 400
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, encoding='utf-8', dtype=str)
        else:
            df = pd.read_excel(file, dtype=str)
            
        df.columns = [str(c).strip() for c in df.columns]
        if not file_key:
            pk_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
            candidate = (pk_cfg.valor if pk_cfg else None) or ''
            file_key = candidate if candidate in df.columns else str(df.columns[0])
        if file_key not in df.columns:
            return jsonify({'error': f'Key {file_key} not found in headers.'}), 400

        # Validación interna: FLM y PEXT deben traer la columna CATEGORY con el valor
        # correcto para evitar importar por error datos de otro proceso/mundo.
        proy_act = Proyecto.query.get(pid)
        proy_act_nombre = proy_act.nombre.strip().upper() if proy_act and proy_act.nombre else ''
        category_esperado = None
        if proy_act_nombre == 'FLM':
            category_esperado = 'O&M CRM'
        elif proy_act_nombre == 'PEXT':
            category_esperado = 'O&M PEXT'
        if category_esperado:
            cat_col = next((c for c in df.columns if c.strip().upper() == 'CATEGORY'), None)
            if cat_col is None:
                return jsonify({'error': f'El archivo no contiene la columna CATEGORY. La importación de {proy_act_nombre} requiere la categoría "{category_esperado}".'}), 400
            valores_cat = {str(v).strip() for v in df[cat_col].dropna().tolist()}
            if valores_cat and not valores_cat.issubset({category_esperado}):
                return jsonify({'error': f'La columna CATEGORY debe contener únicamente "{category_esperado}" para {proy_act_nombre}. Valores detectados: {", ".join(sorted(valores_cat))}.'}), 400

        # Modo columnas manuales: por defecto solo llave + columnas manuales del archivo
        if import_type == 'manual_cols' and not columns_to_keep:
            columns_to_keep = [file_key] + [c for c in manual_columns_list if c in df.columns and c != file_key]

        if columns_to_keep:
            valid_cols = [c for c in columns_to_keep if c in df.columns]
            if file_key not in valid_cols: valid_cols.append(file_key)
            if consolidate_date and date_column and date_column in df.columns and date_column not in valid_cols:
                valid_cols.append(date_column)
            df = df[valid_cols]
        df = df.fillna('')

        if consolidate_date and date_column and date_column in df.columns and len(df) > 0:
            df['_temp_date'] = pd.to_datetime(df[date_column], errors='coerce')
            df = df.sort_values(by='_temp_date', ascending=True, na_position='first')
            df = df.drop_duplicates(subset=[file_key], keep='last')
            df = df.drop(columns=['_temp_date'])
        elif sum_duplicates and len(df) > 0:
            # Smart aggregation: Sum numeric columns, last for the rest
            agg_dict = {}
            for col in df.columns:
                if col == file_key: continue
                
                if sum_type == 'soles':
                    # Clean currency formatting before numeric conversion
                    cleaned_col = df[col].astype(str).str.replace(r'[sS]/\.?\s*', '', regex=True).str.replace(',', '')
                    temp_numeric = pd.to_numeric(cleaned_col, errors='coerce')
                else:
                    temp_numeric = pd.to_numeric(df[col], errors='coerce')
                    
                if not temp_numeric.isna().all():
                    df[col] = temp_numeric.fillna(0)
                    agg_dict[col] = 'sum'
                else:
                    agg_dict[col] = 'last'
            
            if agg_dict:
                df = df.groupby(file_key, as_index=False).agg(agg_dict)
        
        filtros = FiltroMaestro.query.filter_by(proyecto_id=pid).all()
        
        # Agrupar reglas por "Clusters" de columnas (Connected Components)
        # Esto permite que reglas para diferentes columnas se sumen con AND
        # Pero reglas que comparten columnas se sumen con OR
        raw_reglas = []
        for f in filtros:
            cols = [c.strip() for c in f.columna.split(',')]
            vals = [v.strip() for v in f.valor.split(',')]
            raw_reglas.append({'cols': set(cols), 'pairs': list(zip(cols, vals))})
            
        clusters = []
        for r in raw_reglas:
            assigned = False
            for group in clusters:
                # Si la regla comparte alguna columna con el grupo, se une a él
                if any(c in group['columns'] for c in r['cols']):
                    group['columns'].update(r['cols'])
                    group['rules'].append(r['pairs'])
                    assigned = True
                    break
            if not assigned:
                clusters.append({'columns': r['cols'], 'rules': [r['pairs']]})
        
        # Consolidar clusters que puedan haberse cruzado después de unirse por partes
        final_clusters = []
        for c in clusters:
            merged = False
            for f in final_clusters:
                if c['columns'] & f['columns']:
                    f['columns'].update(c['columns'])
                    f['rules'].extend(c['rules'])
                    merged = True
                    break
            if not merged:
                final_clusters.append(c)
            
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

        config_pk = AppConfig.query.filter_by(proyecto_id=pid, clave='primary_key').first()
        system_pk = config_pk.valor if config_pk else None
        
        if import_type == 'base' and not system_pk:
            system_pk = file_key
            db.session.add(AppConfig(proyecto_id=pid, clave='primary_key', valor=system_pk))
            db.session.commit()
            
        # Delta: consultar solo las filas cuyas claves vienen en el archivo,
        # en chunks de 400 (limite de parametros de SQLite) para no traer toda la tabla.
        imported_keys = set()
        for _v in df[file_key].tolist():
            _s = str(_v).strip()
            if _s:
                imported_keys.add(_s)

        existing_records = {}
        if imported_keys:
            key_list = sorted(imported_keys)
            for i in range(0, len(key_list), 400):
                chunk = key_list[i:i + 400]
                chunk_records = NucleusData.query.filter(
                    NucleusData.proyecto_id == pid,
                    NucleusData.key_value.in_(chunk)
                ).all()
                for r in chunk_records:
                    existing_records[r.key_value] = r
        
        # Consolidation Config
        cons_cfg_row = AppConfig.query.filter_by(proyecto_id=pid, clave='consolidation_config').first()
        cons_cfg = json.loads(cons_cfg_row.valor) if cons_cfg_row else {}
        consolidate_on_fail = cons_cfg.get('consolidate_on_filter_fail', False)
        
        updated, added, ignored, consolidated = 0, 0, 0, 0
        dynamic_cols = set()

        WO_STATE_COL = 'Estado de la tarea (WO State)'
        STATE_TS_COL = 'FECHA CAMBIO ESTADO'
        DISPATCHED_TS_COL = '_fecha_dispatched'
        CANCEL_REJECT_TS_COL = '_fecha_cancel_reject'
        DISPATCHED_STATES = {'dispatched'}
        TERMINAL_STATES = {'canceled', 'rejected'}
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        # Campos protegidos: la importación NO pisa los datos editados manualmente.
        # EXCEPCIÓN: en modo 'manual_cols' (Dataper) el archivo ES la fuente de datos manuales.
        protected_fields = set(manual_columns_list)
        protected_fields.update([
            'SERVICIO', 'CIUDAD', 'TECNICO', 'CONTRATA',
            'MOTIVO DE AVERÍA', 'MOTIVO DE AVERIA', 'SOLUCIÓN', 'SOLUCION',
            'LATITUD', 'LONGITUD', 'SE INSTALÓ MUFAS', 'SE INSTALO MUFAS',
            'LATITUD MUFAS', 'LATITUD Mufas', 'LONGITUD MUFAS', 'LONGITUD Mufas',
            'UBICACIÓN DE MUFAS', 'UBICACION DE MUFAS',
            'MATERIALES'
        ])
        
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            key_val = str(row_dict.get(file_key, '')).strip()
            if not key_val: continue
            imported_keys.add(key_val)
            
            # --- 1. MERGE CON DATA EXISTENTE ---
            is_new = False
            if key_val in existing_records:
                record = existing_records[key_val]
                current_data = json.loads(record.data_json)
                old_state = str(current_data.get(WO_STATE_COL, '')).strip()
                if import_type == 'manual_cols':
                    current_data.update(row_dict)
                else:
                    for k, v in row_dict.items():
                        if k in protected_fields and k in current_data:
                            continue
                        current_data[k] = v
                new_state = str(current_data.get(WO_STATE_COL, '')).strip()
                new_state_l = new_state.lower()
                if new_state != old_state:
                    # Registrar TODA transición (incluye quedarse vacío), de modo
                    # que el historial nunca pierda cambios de estado por importación.
                    if new_state_l != old_state.lower():
                        current_data[STATE_TS_COL] = now_str
                        dynamic_cols.add(STATE_TS_COL)
                    db.session.add(HistorialCambios(
                        proyecto_id=pid,
                        usuario_id=None,
                        username='IMPORT',
                        key_value=key_val,
                        campo_modificado=WO_STATE_COL,
                        valor_anterior=old_state,
                        valor_nuevo=new_state,
                        fecha=datetime.utcnow()
                    ))
                if new_state_l in DISPATCHED_STATES and not current_data.get(DISPATCHED_TS_COL):
                    current_data[DISPATCHED_TS_COL] = now_str
                if new_state_l in TERMINAL_STATES and not current_data.get(CANCEL_REJECT_TS_COL):
                    current_data[CANCEL_REJECT_TS_COL] = now_str
            else:
                if import_type == 'cruce':
                    schema_config = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
                    schema_val = json.loads(schema_config.valor) if schema_config else []
                    if schema_val:
                        continue
                current_data = row_dict.copy()
                init_state = str(current_data.get(WO_STATE_COL, '')).strip().lower()
                if init_state:
                    current_data[STATE_TS_COL] = now_str
                    dynamic_cols.add(STATE_TS_COL)
                    db.session.add(HistorialCambios(
                        proyecto_id=pid,
                        usuario_id=None,
                        username='IMPORT',
                        key_value=key_val,
                        campo_modificado=WO_STATE_COL,
                        valor_anterior='',
                        valor_nuevo=str(current_data.get(WO_STATE_COL, '')).strip(),
                        fecha=datetime.utcnow()
                    ))
                if init_state in DISPATCHED_STATES:
                    current_data[DISPATCHED_TS_COL] = now_str
                if init_state in TERMINAL_STATES:
                    current_data[CANCEL_REJECT_TS_COL] = now_str
                is_new = True

            # --- 2. APLICAR REGLAS Y TABLAS MAESTRAS ---
            for regla in reglas:
                match = True
                for c, v in regla['condiciones']:
                    if str(current_data.get(c, '')) != v:
                        match = False; break
                if match:
                    current_data[regla['nueva_columna']] = regla['nuevo_valor']
                    dynamic_cols.add(regla['nueva_columna'])

            # --- 3. LOGICA DE FILTRO POR CLUSTERS ---
            keep_record = True
            if final_clusters:
                for cluster in final_clusters:
                    # Usamos current_data para evaluar. Si es un cruce, ahora tiene la info base también.
                    match_cluster = False
                    for rule in cluster['rules']:
                        match_rule = True
                        for c, v in rule:
                            val_archivo = str(current_data.get(c, '')).strip().upper()
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
            
            # --- 4. DECISIÓN DE CONSOLIDACIÓN ---
            if not keep_record:
                if consolidate_on_fail and key_val in existing_records:
                    record = existing_records[key_val]
                    # Guardamos el current_data (que contiene las actualizaciones del archivo importado) en el histórico
                    new_hist = NucleusHistory(proyecto_id=pid, key_value=key_val, data_json=safe_json_dumps(current_data))
                    db.session.add(new_hist)
                    db.session.delete(record)
                    consolidated += 1
                    updated += 1
                    del existing_records[key_val]
                else:
                    ignored += 1
                continue
                
            # --- 5. GUARDAR REGISTRO ACTIVO ---
            if is_new:
                new_record = NucleusData(proyecto_id=pid, key_value=key_val, data_json=safe_json_dumps(current_data))
                db.session.add(new_record)
                existing_records[key_val] = new_record
                added += 1
            else:
                record = existing_records[key_val]
                record.data_json = safe_json_dumps(current_data)
                updated += 1
        
        # Absence-based Consolidation (Optimized to avoid SQLite parameter limits)
        absent_consolidated = 0
        if import_type == 'base' and cons_cfg.get('auto_consolidate_missing'):
            # Consulta solo la columna key_value (no el data_json pesado)
            # para comparar las claves existentes contra las del archivo.
            all_existing_keys = [r[0] for r in db.session.query(NucleusData.key_value)
                                 .filter(NucleusData.proyecto_id == pid).all()]
            for kv in all_existing_keys:
                if kv not in imported_keys:
                    rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=kv).first()
                    if rec is None:
                        continue
                    new_hist = NucleusHistory(proyecto_id=pid, key_value=rec.key_value, data_json=rec.data_json)
                    db.session.add(new_hist)
                    db.session.delete(rec)
                    absent_consolidated += 1
                    consolidated += 1

        db.session.commit()
        
        config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        schema_cols = set(json.loads(config_schema.valor)) if config_schema else set()
        new_schema = schema_cols.union(set(df.columns)).union(dynamic_cols)
        if new_schema != schema_cols:
            if config_schema:
                config_schema.valor = safe_json_dumps(list(new_schema))
            else:
                db.session.add(AppConfig(proyecto_id=pid, clave='app_schema', valor=safe_json_dumps(list(new_schema))))
            db.session.commit()
        return jsonify({
            'success': True, 
            'added': added, 
            'updated': updated, 
            'ignored': ignored, 
            'consolidated': consolidated,
            'pk': system_pk
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/master/filtros', methods=['GET', 'POST', 'DELETE'])
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

@app.route('/api/master/tablas', methods=['GET', 'POST', 'DELETE'])
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

@app.route('/api/master/reglas_manuales', methods=['GET', 'POST', 'DELETE'])
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

@app.route('/api/master/reprocess', methods=['POST'])
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

@app.route('/api/master/manual_columns', methods=['GET', 'POST', 'DELETE'])
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

@app.route('/api/columns/layout', methods=['GET', 'POST'])
@login_required
def api_columns_layout():
    """Orden y visibilidad de columnas definidos por el admin; se aplican a todos los usuarios."""
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
    if request.method == 'GET':
        return jsonify(json.loads(config.valor) if config and config.valor else [])
    if session.get('rol') != 'admin':
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

@app.route('/api/master/dashboard_charts', methods=['GET', 'POST'])
@login_required
def api_dashboard_charts():
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_charts').first()
    
    if request.method == 'GET':
        charts = json.loads(config.valor) if config else []
        return jsonify(charts)
        
    if request.method == 'POST':
        if session.get('rol') in ['demo', 'gestor']:
            return jsonify({'error': 'Rol sin permisos para modificar el dashboard.'}), 403
        charts = request.json # Expecting an array of chart objects
        if config:
            config.valor = safe_json_dumps(charts)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='saved_dashboard_charts', valor=safe_json_dumps(charts)))
        db.session.commit()
        return jsonify({'success': True})

@app.route('/api/master/dashboard_kpis', methods=['GET', 'POST'])
@login_required
def api_dashboard_kpis():
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_kpis').first()
    
    if request.method == 'GET':
        kpis = json.loads(config.valor) if config else []
        return jsonify(kpis)
        
    if request.method == 'POST':
        if session.get('rol') in ['demo', 'gestor']:
            return jsonify({'error': 'Rol sin permisos para modificar el dashboard.'}), 403
        kpis = request.json
        if config:
            config.valor = safe_json_dumps(kpis)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='saved_dashboard_kpis', valor=safe_json_dumps(kpis)))
        db.session.commit()
        return jsonify({'success': True})

@app.route('/api/master/all_columns')
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

@app.route('/api/master/dashboard_filters', methods=['GET', 'POST'])
@login_required
def api_dashboard_filters():
    pid = session.get('current_proyecto_id')
    config = AppConfig.query.filter_by(proyecto_id=pid, clave='saved_dashboard_filters').first()
    
    if request.method == 'GET':
        filters = json.loads(config.valor) if config else []
        return jsonify(filters)
        
    if request.method == 'POST':
        if session.get('rol') in ['demo', 'gestor']:
            return jsonify({'error': 'Rol sin permisos para modificar filtros del dashboard.'}), 403
        filters = request.json
        if config:
            config.valor = safe_json_dumps(filters)
        else:
            db.session.add(AppConfig(proyecto_id=pid, clave='saved_dashboard_filters', valor=safe_json_dumps(filters)))
        db.session.commit()
        return jsonify({'success': True})

@app.route('/api/config/consolidation', methods=['GET', 'POST'])
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

@app.route('/api/config/cotizacion_margen', methods=['GET', 'POST'])
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

@app.route('/api/master/template/<tipo>')
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

@app.route('/api/master/bulk_import/<tipo>', methods=['POST'])
@login_required
def api_master_bulk_import(tipo):
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para realizar importaciones masivas.'}), 403
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

@app.route('/api/rows/update', methods=['POST'])
@login_required
def api_rows_update():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para actualizar datos.'}), 403
    # SITE: solo supervisor/admin puede editar
    _proy_chk = db.session.get(Proyecto, pid)
    if _proy_chk and _proy_chk.nombre.strip() == 'SITE' and session.get('rol') not in ('admin', 'supervisor'):
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
        
        # Combustible: el gestor solo puede completar información pendiente (campos
        # vacíos); los campos ya registrados solo los edita el admin.
        proy_obj = db.session.get(Proyecto, pid)
        proy_nombre = proy_obj.nombre.strip() if proy_obj and proy_obj.nombre else ''
        if proy_nombre == 'Combustible':
            valor_actual = str(row_dict.get(field, '') or '').strip()
            if session.get('rol') != 'admin' and valor_actual:
                return jsonify({'error': f'El campo {field} ya está registrado. Solo el administrador puede editarlo.'}), 403
            if field == 'GESTOR':
                return jsonify({'error': 'El campo GESTOR no se puede editar. Es quien registró el movimiento.'}), 400
            # WO NUMBER libre: acepta cualquier código (vacío = CM PENDIENTE).
            if field in ('MOVIMIENTO', 'GALONES', 'QR ASIGNADO'):
                new_gen = str(value if field == 'QR ASIGNADO' else row_dict.get('QR ASIGNADO', '')).strip()
                new_mov = str(value if field == 'MOVIMIENTO' else row_dict.get('MOVIMIENTO', '')).strip().upper()
                new_gal = _parse_galones(value if field == 'GALONES' else row_dict.get('GALONES'))
                # Calcular saldo excluyendo ESTE registro (para simular el cambio)
                temp_bal = 0.0
                for r in NucleusData.query.filter_by(proyecto_id=pid).all():
                    if r.id == record.id:
                        continue
                    try:
                        rd = json.loads(r.data_json)
                    except Exception:
                        continue
                    if str(rd.get('QR ASIGNADO', '')).strip() != new_gen:
                        continue
                    rm = str(rd.get('MOVIMIENTO', '')).strip().upper()
                    g = _parse_galones(rd.get('GALONES'))
                    temp_bal = temp_bal + g if rm != 'GASTO' else temp_bal - g
                if new_mov == 'GASTO' and new_gal > temp_bal + 1e-9:
                    return jsonify({'error': f'Saldo insuficiente. Disponible: {temp_bal:g} galones. Se intentó gastar: {new_gal:g}.'}), 400

        # Cotizaciones: GESTOR y la llave (N° COTIZACION) no se editan; una vez
        # GENERADA, solo el admin puede corregir, salvo NUMERO WO cuando está en CM-PENDIENTE.
        if proy_nombre == 'Cotizaciones':
            if field == 'GESTOR':
                return jsonify({'error': 'El campo GESTOR no se puede editar. Es quien registró la cotización.'}), 400
            if field == 'N° COTIZACION':
                return jsonify({'error': 'El N° de cotización es la llave del registro y no se puede editar.'}), 400
            if session.get('rol') != 'admin' and str(row_dict.get('GENERADA', '') or '') == '1':
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
        db.session.commit()
        
        # Inject KPI calculations for instant feedback
        rows_injected, _ = inject_kpis(pid, [row_dict])
        final_row = rows_injected[0]
        
        # Update schema if new tracking columns
        config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        if config_schema:
            schema_cols = set(json.loads(config_schema.valor))
            nuevas_cols = {'_ultimo_usuario_manual', '_fecha_ultima_act_manual'}
            if not nuevas_cols.issubset(schema_cols):
                updated_schema = list(schema_cols.union(nuevas_cols))
                config_schema.valor = safe_json_dumps(updated_schema)
                db.session.commit()
        
        return jsonify({'success': True, 'newData': final_row})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/rows/add', methods=['POST'])
@login_required
def api_rows_add():
    pid = session.get('current_proyecto_id')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para añadir registros.'}), 403
    _proy_chk = db.session.get(Proyecto, pid)
    if _proy_chk and _proy_chk.nombre.strip() == 'SITE' and session.get('rol') not in ('admin', 'supervisor'):
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
                # saldo actual del generador (sin incluir este nuevo gasto)
                saldo = _combustible_saldo(pid, gen)
                if gal_n > saldo + 1e-9:
                    return jsonify({'error': f'Saldo insuficiente. Disponible: {saldo:g} galones. Se intentó gastar: {gal_n:g}.'}), 400

        # Cotizaciones: GESTOR automático y N° correlativo NO editable (avanza desde 0000031).
        if proy_nombre == 'Cotizaciones':
            import re
            from datetime import datetime as _dt
            row_data['GESTOR'] = session.get('username', '')
            yr = str(_dt.now().year)
            maxn = 30
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

        new_record = NucleusData(proyecto_id=pid, key_value=key_val, data_json=json.dumps(row_data))
        db.session.add(new_record)
        db.session.commit()
        
        return jsonify({'success': True, 'key': key_val})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/rows/delete', methods=['POST'])
@login_required
def api_rows_delete():
    pid = session.get('current_proyecto_id')
    # Los gestores pueden eliminar solo en proyectos manuales (Dataper, Material,
    # Site Name, Generadores), nunca en WOs (FLM/PEXT).
    proy_obj = db.session.get(Proyecto, pid) if pid else None
    proy_nombre = proy_obj.nombre.strip() if proy_obj and proy_obj.nombre else ''
    manual = proy_nombre in ('Dataper', 'Material', 'Site Name', 'Generadores', 'Combustible', 'Cotizaciones', 'SITE')
    if session.get('rol') == 'demo':
        return jsonify({'error': 'No tienes permisos para eliminar registros.'}), 403
    if session.get('rol') == 'gestor' and not manual:
        return jsonify({'error': 'No tienes permisos para eliminar registros.'}), 403
    if proy_nombre == 'Combustible' and session.get('rol') != 'admin':
        return jsonify({'error': 'No tienes permisos para eliminar movimientos de Combustible. Solo el administrador puede eliminar lo registrado.'}), 403
    if proy_nombre == 'SITE' and session.get('rol') not in ('admin', 'supervisor'):
        return jsonify({'error': 'Solo supervisor o admin puede eliminar sites.'}), 403
    try:
        data = request.json
        keys = data.get('keys', [])
        if not keys: return jsonify({'error': 'No se especificaron registros para eliminar'}), 400
        
        # Delete records
        NucleusData.query.filter(NucleusData.proyecto_id == pid, NucleusData.key_value.in_(keys)).delete(synchronize_session=False)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- WO DETAIL (Modal de detalle del registro) ---
@app.route('/api/combustible/por_wo', methods=['GET'])
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

@app.route('/api/wo/meta', methods=['GET'])
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

        # Técnicos activos desde DATAPER, filtrados por el PROYECTO actual
        tecnicos = []
        dataper = Proyecto.query.filter_by(nombre='Dataper').first()
        if dataper:
            seen = set()
            for r in NucleusData.query.filter_by(proyecto_id=dataper.id).all():
                try:
                    d = json.loads(r.data_json)
                except Exception:
                    continue
                est = str(d.get('ESTADO') or '').strip().upper()
                if est and est != 'ACTIVO':
                    continue
                pr = str(d.get('PROYECTO') or '').strip()
                if proy_nombre and pr and pr != proy_nombre:
                    continue
                t = str(d.get('TECNICO') or '').strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                tecnicos.append({'nombre': t, 'contrata': str(d.get('CONTRATA') or '').strip()})
        tecnicos.sort(key=lambda x: x['nombre'])

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
                if proy_nombre and pr and pr != proy_nombre:
                    continue
                desc = str(d.get('DESCRIPCION_MATERIAL') or '').strip()
                if not desc or desc in seen:
                    continue
                seen.add(desc)
                materiales.append({
                    'codigo': str(d.get('COD_MATERIAL') or '').strip(),
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

@app.route('/api/wo/servicios', methods=['POST'])
@login_required
def api_wo_servicios():
    pid = session.get('current_proyecto_id')
    if session.get('rol') not in ['admin', 'supervisor']:
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

@app.route('/api/wo/historial', methods=['GET'])
@login_required
def api_wo_historial():
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


@app.route('/api/rows/bulk_update', methods=['POST'])
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
        db.session.commit()

        rows_injected, _ = inject_kpis(pid, [row_dict])
        final_row = rows_injected[0]

        # Update schema if new tracking columns
        config_schema = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
        if config_schema:
            schema_cols = set(json.loads(config_schema.valor))
            nuevas_cols = {'_ultimo_usuario_manual', '_fecha_ultima_act_manual', 'FECHA CAMBIO ESTADO'}
            if not nuevas_cols.issubset(schema_cols):
                updated_schema = list(schema_cols.union(nuevas_cols))
                config_schema.valor = safe_json_dumps(updated_schema)
                db.session.commit()

        return jsonify({'success': True, 'newData': final_row})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/init_manual', methods=['POST'])
@login_required
def api_config_init_manual():
    pid = session.get('current_proyecto_id')
    if session.get('rol') not in ['admin', 'supervisor']:
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

@app.route('/api/clean', methods=['POST'])
@login_required
def api_clean():
    if session.get('rol') in ['gestor', 'demo']:
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


# --- Evidencia fotográfica (Tiempo Inicio / Proceso / Cierre) ---
EVIDENCIA_TIPOS = ('inicio', 'proceso', 'cierre')
EVIDENCIA_MAX_POR_TIPO = 5
EVIDENCIA_EXT_ALLOWED = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic'}

def evidencia_folder(pid, key):
    return os.path.join(app.config['EVIDENCIA_DIR'], str(pid), secure_filename(str(key)))

def evidencia_limpiar_slot(pid, key, tipo, indice):
    folder = evidencia_folder(pid, key)
    for old in glob.glob(os.path.join(folder, f'{tipo}_{int(indice)}.*')):
        try:
            os.remove(old)
        except Exception:
            pass

def evidencia_comprimir(ruta, calidad=None, max_lado=None):
    """Comprime y redimensiona una imagen para ahorrar almacenamiento.
    Devuelve True si se comprimió correctamente; si no puede (ej. HEIC),
    deja el archivo original tal cual."""
    calidad = calidad if calidad is not None else app.config['EVIDENCIA_CALIDAD']
    max_lado = max_lado if max_lado is not None else app.config['EVIDENCIA_MAX_LADO']
    try:
        img = Image.open(ruta)
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert('RGB')
        w, h = img.size
        lado_max = max(w, h)
        if lado_max > max_lado:
            ratio = max_lado / lado_max
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
        img.save(ruta, 'JPEG', quality=calidad, optimize=True)
        return True
    except Exception:
        return False

def evidencia_usa_b2():
    return bool(app.config.get('B2_BUCKET') and app.config.get('B2_KEY_ID') and app.config.get('B2_APP_KEY'))

def b2_cliente():
    import boto3
    endpoint = app.config['B2_ENDPOINT_URL'] or f"https://s3.{app.config['B2_REGION']}.backblazeb2.com"
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=app.config['B2_KEY_ID'],
        aws_secret_access_key=app.config['B2_APP_KEY'],
        region_name=app.config['B2_REGION'],
    )

def evidencia_eliminar_b2(key, tipo, indice):
    client = b2_cliente()
    bucket = app.config['B2_BUCKET']
    prefix = f'{key}/{tipo}_{int(indice)}.'
    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for o in resp.get('Contents', []):
            client.delete_object(Bucket=bucket, Key=o['Key'])
    except Exception:
        pass

@app.route('/api/evidencia/subir', methods=['POST'])
@login_required
def api_evidencia_subir():
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos para subir evidencia.'}), 403
    pid = session.get('current_proyecto_id')
    key = (request.form.get('key') or '').strip()
    tipo = (request.form.get('tipo') or '').strip().lower()
    try:
        indice = int(request.form.get('indice'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Índice inválido'}), 400
    file = request.files.get('foto')
    if not key or tipo not in EVIDENCIA_TIPOS + ('comb',):
        return jsonify({'error': 'Datos incompletos'}), 400
    if indice < 0 or indice >= EVIDENCIA_MAX_POR_TIPO:
        return jsonify({'error': 'Índice fuera de rango'}), 400
    if file is None or not file.filename:
        return jsonify({'error': 'No se recibió ningún archivo'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in EVIDENCIA_EXT_ALLOWED:
        return jsonify({'error': f'Formato no permitido: {ext}. Usa {", ".join(sorted(EVIDENCIA_EXT_ALLOWED))}'}), 400

    # Guardar a un archivo temporal, comprimir y luego mover/subir.
    fd, ruta_tmp = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        file.save(ruta_tmp)
        nombre = f'{tipo}_{indice}{ext}'
        if evidencia_comprimir(ruta_tmp):
            if not nombre.lower().endswith('.jpg'):
                nueva = ruta_tmp + '.jpg'
                os.rename(ruta_tmp, nueva)
                ruta_tmp = nueva
                nombre = f'{tipo}_{indice}.jpg'

        if evidencia_usa_b2():
            evidencia_eliminar_b2(key, tipo, indice)
            b2_cliente().upload_file(ruta_tmp, app.config['B2_BUCKET'], f'{key}/{nombre}')
        else:
            folder = evidencia_folder(pid, key)
            os.makedirs(folder, exist_ok=True)
            evidencia_limpiar_slot(pid, key, tipo, indice)
            os.replace(ruta_tmp, os.path.join(folder, nombre))

        url = f'/api/evidencia/foto/{pid}/{secure_filename(str(key))}/{nombre}?v={int(time.time())}'
        return jsonify({'success': True, 'url': url})
    finally:
        if os.path.exists(ruta_tmp):
            try:
                os.remove(ruta_tmp)
            except Exception:
                pass

@app.route('/api/evidencia/eliminar', methods=['POST'])
@login_required
def api_evidencia_eliminar():
    if session.get('rol') == 'demo':
        return jsonify({'error': 'Rol DEMO no tiene permisos.'}), 403
    pid = session.get('current_proyecto_id')
    data = request.json or {}
    key = (data.get('key') or '').strip()
    tipo = (data.get('tipo') or '').strip().lower()
    try:
        indice = int(data.get('indice'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Índice inválido'}), 400
    if not key or tipo not in EVIDENCIA_TIPOS or indice < 0 or indice >= EVIDENCIA_MAX_POR_TIPO:
        return jsonify({'error': 'Datos incompletos'}), 400
    if evidencia_usa_b2():
        evidencia_eliminar_b2(key, tipo, indice)
    else:
        evidencia_limpiar_slot(pid, key, tipo, indice)
    return jsonify({'success': True})

@app.route('/api/evidencia/foto/<int:pid>/<path:key>/<path:nombre>')
@login_required
def api_evidencia_foto(pid, key, nombre):
    if pid != session.get('current_proyecto_id'):
        return jsonify({'error': 'Acceso denegado'}), 403
    nombre = os.path.basename(nombre)
    if evidencia_usa_b2():
        try:
            obj = b2_cliente().get_object(Bucket=app.config['B2_BUCKET'], Key=f'{key}/{nombre}')
            data = obj['Body'].read()
            mt = mimetypes.guess_type(nombre)[0] or 'application/octet-stream'
            resp = Response(data, mimetype=mt)
            resp.headers['Cache-Control'] = 'private, max-age=604800, immutable'
            return resp
        except Exception:
            return jsonify({'error': 'No encontrado'}), 404
    folder = evidencia_folder(pid, key)
    return send_from_directory(folder, nombre, max_age=604800)

@app.route('/healthz')
def healthz():
    return 'OK', 200

# ---- COTIZACION -------------------------------------------------------
@app.route('/api/cotizacion/estado', methods=['GET'])
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

@app.route('/api/cotizacion/lista', methods=['GET'])
@login_required
def api_cotizacion_lista():
    """Devuelve todas las cotizaciones del ticket (puede haber varias)."""
    pid = session.get('current_proyecto_id')
    key = request.args.get('key', '').strip()
    if not pid or not key:
        return jsonify({'lista': []})
    cots = Cotizacion.query.filter_by(proyecto_id=pid, key_value=key).order_by(Cotizacion.id.asc()).all()
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

@app.route('/api/cotizacion/registro', methods=['GET'])
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

@app.route('/api/cotizacion/descargar_registro', methods=['POST'])
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


def _cotizacion_registro_pdf_response(rec):
    """Construye el PDF Cobra desde un registro del módulo Cotizaciones.
    Solo si la cotización ya fue GENERADA (bloqueo respetado en todas las vías).
    Si NUMERO WO está vacío, muestra CM-PENDIENTE como en Combustible."""
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    if str(d.get('GENERADA', '') or '') != '1':
        return jsonify({'error': 'La cotización aún no ha sido generada. Usa "Generar Cotización" primero.'}), 400
    try:
        items = json.loads(d.get('ITEMS_JSON') or '[]')
    except Exception:
        items = []
    numero = str(d.get('N° COTIZACION', '') or '')
    # NUMERO WO → CM-PENDIENTE si está vacío, igual que Combustible
    numero_wo = str(d.get('NUMERO WO', '') or '').strip()
    ticket_raw = str(d.get('TICKET', '') or '').strip()
    # Para el PDF, el campo TICKET muestra el NUMERO WO asociado o CM-PENDIENTE
    pdf_ticket = numero_wo if numero_wo else "CM-PENDIENTE"
    # Si TICKET tiene valor y es distinto, lo anteponemos, pero si es igual o vacío, usamos el display
    if ticket_raw and ticket_raw != numero_wo and ticket_raw != "CM-PENDIENTE":
        # Si ambos tienen valor y son distintos, priorizar NUMERO WO pero dejar constancia
        # Por ahora, mostrar NUMERO WO (con CM-PENDIENTE si vacío)
        pass
    pdf_bytes = _generar_pdf_cotizacion_cobra(
        numero=numero,
        site=str(d.get('SITE', '') or ''),
        supervisor=str(d.get('SUPERVISOR', '') or ''),
        objetivo=str(d.get('OBJETIVO', '') or ''),
        ticket=pdf_ticket,
        elaborado_por=str(d.get('GESTOR', '') or session.get('username', '')),
        items=items
    )
    from flask import make_response
    resp = make_response(pdf_bytes)
    safe_num = numero.replace('/', '-').replace(' ', '_') or 'cotizacion'
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Cotizacion_{safe_num}.pdf'
    return resp


def _obtener_registro_cotizacion():
    """Valida proyecto actual = Cotizaciones y devuelve el registro por key."""
    data = request.json or {}
    key_val = str(data.get('key', '')).strip()
    pid = session.get('current_proyecto_id')
    proy_obj = db.session.get(Proyecto, pid)
    if not key_val:
        return None, None, ({'error': 'Falta la clave del registro'}, 400)
    if not proy_obj or (proy_obj.nombre or '').strip().lower() != 'cotizaciones':
        return None, None, ({'error': 'Proyecto inválido'}, 400)
    rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=key_val).first()
    if not rec:
        return None, None, ({'error': 'Cotización no encontrada'}, 404)
    return rec, proy_obj, None


@app.route('/api/cotizacion/registro_pdf', methods=['POST'])
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

@app.route('/api/cotizacion/registro_generar', methods=['POST'])
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

@app.route('/api/cotizacion/desbloquear', methods=['POST'])
@login_required
def api_cotizacion_desbloquear():
    """Solo admin puede desbloquear una cotización para permitir edición."""
    if session.get('rol') != 'admin':
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

@app.route('/api/cotizacion/eliminar', methods=['POST'])
@login_required
def api_cotizacion_eliminar():
    """Solo admin puede eliminar una cotización."""
    if session.get('rol') != 'admin':
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

@app.route('/api/cotizacion/generar', methods=['POST'])
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
        if cot_existente and cot_existente.bloqueada and user_rol != 'admin':
            return jsonify({'error': 'La cotización ya fue generada y está bloqueada. Solo admin puede modificarla.'}), 403

    numero = data.get('numero', '').strip()
    nota = data.get('nota', '').strip()
    gastos = data.get('gastos', [])
    mano_obra = data.get('mano_obra', [])

    # Formato Cobra (FLM): items unicos con TIPO/UND/FEE
    formato = str(data.get('formato', '') or '').strip().lower()
    site = str(data.get('site', '') or '').strip()
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


def _generar_pdf_cotizacion(numero, nota, ticket, cotizado_por, revisado_por, fecha, gastos, mano_obra):
    """Genera el PDF de cotización con el formato exacto de la imagen."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.pdfgen import canvas
    from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame

    buf = io.BytesIO()
    PAGE_W, PAGE_H = landscape(A4)
    M = 6 * mm  # margen

    # Colores corporativos
    NAVY = colors.HexColor('#1B3A6B')
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor('#F2F2F2')
    MID_GRAY = colors.HexColor('#D9D9D9')
    DARK = colors.HexColor('#1a1a1a')

    def fmt_soles(v):
        try:
            f = float(v)
            return f'S/ {f:,.2f}'
        except:
            return 'S/ -'

    def safe_str(v):
        return str(v) if v is not None else ''

    # Calcular subtotales
    subtotal_a = sum(float(g.get('total_p', 0) or 0) for g in gastos)
    subtotal_b = sum(float(m.get('total_p', 0) or 0) for m in mano_obra)
    total_ab = subtotal_a + subtotal_b

    # Estilos de párrafo
    style_normal = ParagraphStyle('normal', fontName='Helvetica', fontSize=7, leading=8)
    style_bold = ParagraphStyle('bold', fontName='Helvetica-Bold', fontSize=7, leading=8)
    style_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=NAVY)
    style_header_white = ParagraphStyle('hw', fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=WHITE)
    style_section = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=WHITE)
    style_right = ParagraphStyle('right', fontName='Helvetica', fontSize=7, leading=8, alignment=TA_RIGHT)
    style_right_bold = ParagraphStyle('rb', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                             leftMargin=M, rightMargin=M,
                             topMargin=M, bottomMargin=M)
    W = PAGE_W - 2 * M
    story = []

    # ---- CABECERA: Logo | N° Cotización ---
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'cobra-logo.png')
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=30*mm, height=17*mm)
    else:
        logo = Paragraph('<b>cobra</b>', style_title)

    num_para = Paragraph(f'<b>N° Cotización :&nbsp;&nbsp;&nbsp;{numero}</b>', style_title)
    header_data = [[logo, num_para]]
    header_tbl = Table(header_data, colWidths=[W * 0.4, W * 0.6])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 1.5 * mm))

    # ---- SECCIÓN A: DATOS DEL CLIENTE ---
    def section_row(label):
        return [Paragraph(f'<b>{label}</b>', style_header_white), '', '', '']

    def client_row(label, value, label2='', value2=''):
        cells = [
            Paragraph(f'<b>{label}</b>', style_bold),
            Paragraph(safe_str(value), style_normal),
            Paragraph(f'<b>{label2}</b>', style_bold) if label2 else '',
            Paragraph(safe_str(value2), style_normal) if value2 else '',
        ]
        return cells

    c1 = W * 0.18
    c2 = W * 0.42
    c3 = W * 0.12
    c4 = W * 0.28

    sec_a_data = [
        [Paragraph('<b>A: DATOS DEL CLIENTE</b>', style_header_white), '', '', ''],
        client_row('Cliente:', 'HUAWEI DEL PERU', 'RUC:', '20507646728'),
        client_row('Domicilio:', 'Cal. las Begonias Nro. 415 Int. 2301'),
        client_row('Solicitado por:', 'Even Vivar'),
        client_row('Validador:', 'Sergio Huaman'),
        client_row('Nota:', nota or ''),
    ]
    sec_a_tbl = Table(sec_a_data, colWidths=[c1, c2, c3, c4])
    sec_a_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('SPAN', (0, 0), (-1, 0)),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, 2), (3, 2)),
        ('SPAN', (1, 3), (3, 3)),
        ('SPAN', (1, 4), (3, 4)),
        ('SPAN', (1, 5), (3, 5)),
    ]))
    story.append(sec_a_tbl)
    story.append(Spacer(1, 1 * mm))

    # ---- SECCIÓN B: DATOS DE COTIZACIÓN ---
    sec_b_data = [
        [Paragraph('<b>B: DATOS DE COTIZACION</b>', style_header_white), '', '', ''],
        client_row('Cotizado por:', 'Dennis Unton', 'Fecha:', fecha),
        client_row('Revisado por:', 'Dennis Unton', 'Fecha:', fecha),
    ]
    sec_b_tbl = Table(sec_b_data, colWidths=[c1, c2, c3, c4])
    sec_b_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('SPAN', (0, 0), (-1, 0)),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sec_b_tbl)
    story.append(Spacer(1, 1 * mm))

    # ---- TABLA 1: Materiales, Herramientas y/o Homologaciones ---
    col_item = W * 0.06
    col_cod  = W * 0.07
    col_desc = W * 0.30
    col_unid = W * 0.07
    col_cant = W * 0.08
    col_pu   = W * 0.18
    col_tp   = W * 0.24

    t1_cols = [col_item, col_cod, col_desc, col_unid, col_cant, col_pu, col_tp]

    t1_header_sub = [Paragraph('<b>1. Materiales,  Herramientas y/o Homologaciones</b>', style_section), '', '', '', '', '', '']
    t1_col_header = [
        Paragraph('<b>Item</b>', style_bold),
        Paragraph('<b>Cod.</b>', style_bold),
        Paragraph('<b>Descripción</b>', style_bold),
        Paragraph('<b>Unid</b>', style_bold),
        Paragraph('<b>Cant</b>', style_bold),
        Paragraph('<b>Precio unid.</b>', style_bold),
        Paragraph('<b>Total P.</b>', style_bold),
    ]

    t1_rows = [t1_header_sub, t1_col_header]
    MAX_ROWS_1 = max(len(gastos), 2)
    for i in range(MAX_ROWS_1):
        if i < len(gastos):
            g = gastos[i]
            row = [
                Paragraph(safe_str(g.get('item', i+1)), style_normal),
                Paragraph(safe_str(g.get('cod', 'SC')), style_normal),
                Paragraph(safe_str(g.get('descripcion', '')), style_normal),
                Paragraph(safe_str(g.get('unid', '')), style_normal),
                Paragraph(safe_str(g.get('cant', '')), style_normal),
                Paragraph(fmt_soles(g.get('precio_unid', '')), style_right),
                Paragraph(fmt_soles(g.get('total_p', '')), style_right),
            ]
        else:
            row = ['', '', '', '', '', Paragraph('S/', style_right), Paragraph('-', style_right)]
        t1_rows.append(row)

    # Fila Total subtotal A
    t1_rows.append([
        '', '', '', '', '', '',
        '',
    ])
    t1_rows.append([
        Paragraph('<b>Total</b>', style_bold), '', '', '', '', '',
        Paragraph(f'<b>Subtotal_A&nbsp;&nbsp;&nbsp;{fmt_soles(subtotal_a)}</b>', style_right_bold),
    ])

    t1_tbl = Table(t1_rows, colWidths=t1_cols)
    n_data_rows_1 = len(t1_rows)
    t1_style = [
        # Sub-header navy
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('SPAN', (0, 0), (-1, 0)),
        # Col header
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 2), (-1, n_data_rows_1-3), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Total row
        ('BACKGROUND', (0, n_data_rows_1-1), (-1, n_data_rows_1-1), LIGHT_GRAY),
        ('SPAN', (0, n_data_rows_1-1), (4, n_data_rows_1-1)),
        ('SPAN', (5, n_data_rows_1-1), (5, n_data_rows_1-1)),
    ]
    t1_tbl.setStyle(TableStyle(t1_style))
    story.append(t1_tbl)
    story.append(Spacer(1, 1.5 * mm))

    # ---- TABLA 2: Mano de Obra ---
    t2_cols = [col_item, col_cod, col_desc, col_unid, col_cant, col_pu, col_tp]

    t2_header_sub = [Paragraph('<b>2. Mano de Obra</b>', style_section), '', '', '', '', '', '']
    t2_col_header = [
        Paragraph('<b>Item</b>', style_bold),
        Paragraph('<b>Cod.</b>', style_bold),
        Paragraph('<b>Descripción</b>', style_bold),
        Paragraph('<b>Unid</b>', style_bold),
        Paragraph('<b>Cant</b>', style_bold),
        Paragraph('<b>Precio unid.</b>', style_bold),
        Paragraph('<b>Total P.</b>', style_bold),
    ]

    t2_rows = [t2_header_sub, t2_col_header]
    MAX_ROWS_2 = max(len(mano_obra), 2)
    for i in range(MAX_ROWS_2):
        if i < len(mano_obra):
            m = mano_obra[i]
            row = [
                Paragraph(safe_str(m.get('item', i+1)), style_normal),
                Paragraph(safe_str(m.get('cod', 'SC')), style_normal),
                Paragraph(safe_str(m.get('descripcion', '')), style_normal),
                Paragraph(safe_str(m.get('unid', '')), style_normal),
                Paragraph(safe_str(m.get('cant', '')), style_normal),
                Paragraph(fmt_soles(m.get('precio_unid', '')), style_right),
                Paragraph(fmt_soles(m.get('total_p', '')), style_right),
            ]
        else:
            row = ['', '', '', '', '', '', '']
        t2_rows.append(row)

    t2_rows.append([
        Paragraph('<b>Total</b>', style_bold), '', '', '', '', '',
        Paragraph(f'<b>Subtotal_B&nbsp;&nbsp;&nbsp;{fmt_soles(subtotal_b)}</b>', style_right_bold),
    ])

    t2_tbl = Table(t2_rows, colWidths=t2_cols)
    n_data_rows_2 = len(t2_rows)
    t2_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 2), (-1, n_data_rows_2-2), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, n_data_rows_2-1), (-1, n_data_rows_2-1), LIGHT_GRAY),
        ('SPAN', (0, n_data_rows_2-1), (5, n_data_rows_2-1)),
    ]
    t2_tbl.setStyle(TableStyle(t2_style))
    story.append(t2_tbl)
    story.append(Spacer(1, 2 * mm))

    # ---- CONDICIONES COMERCIALES + TOTAL FINAL ---
    # Layout exacto de la imagen:
    # [Condiciones Comerciales | (vacío) | (vacío) | (vacío)]
    # [texto condiciones       | Total Cotización (A+B) | S/ | monto]
    try:
        total_val = f'{total_ab:,.2f}'
    except:
        total_val = '0.00'

    cond_col_left = W * 0.50
    cond_col_mid  = W * 0.25
    cond_col_soles = W * 0.07
    cond_col_monto = W * 0.18

    style_cond_hdr = ParagraphStyle('condh', fontName='Helvetica-Bold', fontSize=7, leading=9)
    style_cond_body = ParagraphStyle('condb', fontName='Helvetica', fontSize=7, leading=10)
    style_total_label = ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER)
    style_soles = ParagraphStyle('sol', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER)
    style_monto = ParagraphStyle('mnt', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_RIGHT)

    cond_lines = 'Moneda Nacional soles (S/)<br/>Pagos Según contrato<br/>No incluye IGV'
    cond_data = [
        [
            Paragraph('<b>Condiciones Comerciales</b>', style_cond_hdr),
            '', '', ''
        ],
        [
            Paragraph(cond_lines, style_cond_body),
            Paragraph('<b>Total Cotización (A+B)</b>', style_total_label),
            Paragraph('<b>S/</b>', style_soles),
            Paragraph(f'<b>{total_val}</b>', style_monto),
        ],
    ]
    cond_tbl = Table(cond_data, colWidths=[cond_col_left, cond_col_mid, cond_col_soles, cond_col_monto])
    cond_tbl.setStyle(TableStyle([
        ('BOX',  (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_GRAY),
        ('SPAN', (0, 0), (-1, 0)),
        # Data row bg
        ('BACKGROUND', (0, 1), (0, 1), WHITE),
        ('BACKGROUND', (1, 1), (3, 1), LIGHT_GRAY),
        # Padding
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 1), (3, 1), 'RIGHT'),
    ]))
    story.append(cond_tbl)

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _fecha_larga_es(fecha=None):
    """Fecha en formato largo español: 'viernes, 21 de Agosto de 2026'."""
    DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
             'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    f = fecha or datetime.now()
    return f'{DIAS[f.weekday()]}, {f.day} de {MESES[f.month - 1]} de {f.year}'


def _generar_pdf_cotizacion_cobra(numero, site, supervisor, objetivo, ticket, elaborado_por, items):
    """
    Genera el PDF de cotizacion FLM con el formato Cobra:
    cabecera (FECHA/EMPRESA/DIRIGIDO A/SITE/N COTIZACION/OBJETIVO + RESPONSABLE/
    ELABORADO POR/SUPERVISOR/TICKET), tabla unica de items con FEE y secciones
    fijas de cierre.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    PAGE_W, PAGE_H = landscape(A4)
    M = 8 * mm

    NAVY = colors.HexColor('#1F4E79')
    STEEL = colors.HexColor('#2E75B6')
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor('#F2F2F2')
    MID_GRAY = colors.HexColor('#BFBFBF')
    YELLOW = colors.HexColor('#FFF2CC')
    DARK = colors.HexColor('#1a1a1a')

    def safe_str(v):
        return str(v) if v is not None else ''

    def fmt_soles(v):
        try:
            return f'S/ {float(v):,.2f}'
        except Exception:
            return 'S/ 0.00'

    def fmt_num(v):
        try:
            f = float(v)
            return ('%g' % f) if f == int(f) else f'{f:,.2f}'
        except Exception:
            return ''

    # ---- Estilos ----
    st_norm = ParagraphStyle('n', fontName='Helvetica', fontSize=8, leading=10)
    st_bold = ParagraphStyle('b', fontName='Helvetica-Bold', fontSize=8, leading=10)
    st_hdr_w = ParagraphStyle('hw', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=WHITE)
    st_sec = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=DARK)
    st_cell_c = ParagraphStyle('cc', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_CENTER)
    st_cell_r = ParagraphStyle('cr', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=M, rightMargin=M,
                            topMargin=M, bottomMargin=M)
    W = PAGE_W - 2 * M
    story = []

    # ---- LOGO + Supplier name and RUC No ----
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'cobra-logo.png')
    logo_cell = []
    if os.path.exists(logo_path):
        logo_cell.append(RLImage(logo_path, width=42 * mm, height=20 * mm))
    else:
        logo_cell.append(Paragraph('<b>cobra</b>', ParagraphStyle(
            'lg', fontName='Helvetica-Bold', fontSize=22, leading=24, textColor=NAVY)))
    logo_cell.append(Paragraph('<b>Supplier name and RUC No</b>', ParagraphStyle(
        'sn', fontName='Helvetica-Bold', fontSize=8, leading=10)))

    fecha_str = _fecha_larga_es()
    num_para = Paragraph(f'<b>N° COTIZACIÓN :&nbsp;&nbsp;&nbsp;&nbsp;{safe_str(numero)}</b>',
                         ParagraphStyle('np', fontName='Helvetica-Bold', fontSize=12, leading=15))
    head_tbl = Table([[logo_cell, num_para]], colWidths=[W * 0.45, W * 0.55])
    head_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(head_tbl)
    story.append(Spacer(1, 2 * mm))

    # ---- CABECERA DE DATOS (4 columnas) ----
    c1, c2, c3, c4 = W * 0.14, W * 0.36, W * 0.14, W * 0.36

    def row_lbl(lbl, val, lbl2='', val2=''):
        return [
            Paragraph(f'<b>{lbl}</b>', st_bold),
            Paragraph(safe_str(val), st_norm),
            Paragraph(f'<b>{lbl2}</b>', st_bold) if lbl2 else '',
            Paragraph(safe_str(val2), st_norm) if val2 else '',
        ]

    hdr_data = [
        row_lbl('FECHA:', fecha_str),
        row_lbl('EMPRESA:', 'Cobra Perú'),
        row_lbl('DIRIGIDO A :', 'Huawei del Perú', 'RESPONSABLE', 'Dennis Unton'),
        row_lbl('SITE:', site, 'ELABORADO POR', elaborado_por),
        row_lbl('N° COTIZACIÓN :', numero, 'SUPERVISOR', supervisor),
        row_lbl('OBJETIVO:', objetivo, 'TICKET', ticket),
    ]
    hdr_tbl = Table(hdr_data, colWidths=[c1, c2, c3, c4])
    hdr_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, MID_GRAY),
        ('BACKGROUND', (0, 0), (0, -1), LIGHT_GRAY),
        ('BACKGROUND', (2, 0), (2, -1), LIGHT_GRAY),
        # N° COTIZACION resaltado en amarillo
        ('BACKGROUND', (0, 4), (1, 4), YELLOW),
        ('SPAN', (1, 0), (3, 0)),   # FECHA valor ancho
        ('SPAN', (1, 1), (3, 1)),   # EMPRESA valor ancho
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 3 * mm))

    # ---- TABLA DE ITEMS ----
    col_correl = W * 0.065
    col_tipo = W * 0.09
    col_texto = W * 0.27
    col_und = W * 0.055
    col_cant = W * 0.065
    col_vu = W * 0.10
    col_fee = W * 0.06
    col_vt = W * 0.115
    col_coment = W * 0.18
    it_cols = [col_correl, col_tipo, col_texto, col_und, col_cant, col_vu, col_fee, col_vt, col_coment]

    it_header = [
        Paragraph('<b>CORRELATIVO</b>', st_hdr_w),
        Paragraph('<b>TIPO</b>', st_hdr_w),
        Paragraph('<b>TEXTO EXPLICATIVO</b>', st_hdr_w),
        Paragraph('<b>UND</b>', st_hdr_w),
        Paragraph('<b>CANTIDAD</b>', st_hdr_w),
        Paragraph('<b>VALOR UNITARIO</b>', st_hdr_w),
        Paragraph('<b>FEE %</b>', st_hdr_w),
        Paragraph('<b>VALOR TOTAL</b>', st_hdr_w),
        Paragraph('<b>COMENTARIOS</b>', st_hdr_w),
    ]

    it_rows = [it_header]
    items_ok = []
    for i, it in enumerate(items or []):
        try:
            cant = float(str(it.get('cantidad', '') or 0).replace(',', '.'))
        except Exception:
            cant = 0.0
        try:
            vu = float(str(it.get('valor_unitario', '') or 0).replace(',', '.'))
        except Exception:
            vu = 0.0
        tipo = str(it.get('tipo', '') or '').strip().upper()
        fee = 5.0 if tipo == 'REEMBOLSABLE' else 0.0
        vt = cant * vu * (1 + fee / 100.0)
        items_ok.append(vt)
        it_rows.append([
            Paragraph(str(i + 1), st_cell_c),
            Paragraph(safe_str(tipo), st_cell_c),
            Paragraph(safe_str(it.get('texto', '')), st_norm),
            Paragraph(safe_str(it.get('und', '')), st_cell_c),
            Paragraph(fmt_num(cant), st_cell_r),
            Paragraph(fmt_soles(vu), st_cell_r),
            Paragraph(f'{fee:g}%', st_cell_c),
            Paragraph(fmt_soles(vt), st_cell_r),
            Paragraph(safe_str(it.get('comentarios', '')), st_norm),
        ])

    total_fee = sum(items_ok)
    it_rows.append([
        '', '', '', '', '', '',
        Paragraph('<b>sub total + FEE</b>', st_bold),
        Paragraph(f'<b>{fmt_soles(total_fee)}</b>', st_cell_r),
        '',
    ])

    n_it = len(it_rows)
    it_tbl = Table(it_rows, colWidths=it_cols, repeatRows=1)
    it_style = [
        ('BACKGROUND', (0, 0), (-1, 0), STEEL),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.4, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, max(n_it - 2, 1)), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Fila total resaltada
        ('BACKGROUND', (0, n_it - 1), (-1, n_it - 1), YELLOW),
        ('SPAN', (0, n_it - 1), (5, n_it - 1)),
        ('ALIGN', (6, n_it - 1), (7, n_it - 1), 'RIGHT'),
    ]
    if not items_ok:
        it_style.append(('SPAN', (0, 1), (-1, 1)))
        it_rows.append([Paragraph('Sin items registrados.', st_norm), '', '', '', '', '', '', '', ''])
    it_tbl.setStyle(TableStyle(it_style))
    story.append(it_tbl)
    story.append(Spacer(1, 4 * mm))

    # ---- SECCIONES FIJAS DE CIERRE ----
    secciones_cierre = {
        'TIEMPO DE ENTREGA': '',
        'LUGAR DE ENTREGA': 'En la puerta del site',
        'VALIDEZ DE LA OFERTA': '15 días calendario',
        'CONDICIONES GENERALES': ''
    }
    for titulo, contenido in secciones_cierre.items():
        sec_tbl = Table([[Paragraph(f'<b>{titulo}</b>', st_sec)]], colWidths=[W])
        sec_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, MID_GRAY),
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(sec_tbl)
        if contenido:
            body_tbl = Table([[Paragraph(contenido, st_norm)]], colWidths=[W])
            body_tbl.setStyle(TableStyle([
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(body_tbl)
        story.append(Spacer(1, 1.5 * mm))

    doc.build(story)
    buf.seek(0)
    return buf.read()

# ── Mapa SITE ──────────────────────────────────────────────────────────
@app.route('/mapa-site')
@app.route('/mapa')
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
    if user_rol not in ('admin', 'demo'):
        # Debe tener FLM para ver el mapa de sites
        flm = Proyecto.query.filter_by(nombre='FLM').first()
        has_flm = False
        if flm:
            has_flm = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=flm.id).first() is not None
        if not has_flm:
            has_flm = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=proy_site.id).first() is not None
        if not has_flm:
            from flask import redirect, url_for
            return redirect(url_for('index'))
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

@app.route('/api/sites')
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
        sites.append({
            'codigo': d.get('Código Site', '') or d.get('Codigo Site', '') or r.key_value,
            'nombre': d.get('Nombre Site', ''),
            'lat': lat,
            'lng': lng,
            'estado': d.get('Estado', ''),
            'prioridad': d.get('Prioridad', ''),
            'departamento': d.get('Departamento', ''),
            'provincia': d.get('Provincia', ''),
            'distrito': d.get('Distrito', ''),
            'direccion': d.get('Dirección', '') or d.get('Direccion', ''),
            'region': d.get('Región', '') or d.get('Region', ''),
            'supervisor': d.get('SUPERVISOR', ''),
        })
    return jsonify(sites)

# -----------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
