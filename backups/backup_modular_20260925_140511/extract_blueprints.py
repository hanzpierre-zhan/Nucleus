# -*- coding: utf-8 -*-
import re, os

SRC = r'backups\backup_20260925_124858\app.py'
text = open(SRC, encoding='utf-8', errors='replace').read()

HEADER = '''\
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
from services.utilidades import (login_required, safe_json_dumps, inject_kpis,
                                  apply_data_restrictions, get_session_info,
                                  get_menu_proyectos, PROYECTOS_FIJOS,
                                  PROYECTOS_REMOVIDOS)
'''

BLUEPRINT_MAP = [
    ('auth', '', [
        'login', 'logout', 'cambiar_password', 'switch_project',
    ]),
    ('pages', '', [
        'index', 'dashboard', 'configuraciones', 'admin_panel',
        'proyectos_page', 'usuarios_page', 'healthz', 'mapa_site',
    ]),
    ('admin', '/api', [
        'api_admin_proyecto', 'api_tecnicos', 'api_admin_usuario',
        'api_admin_usuario_duplicar', 'api_admin_permisos',
        'api_admin_columnas', 'api_column_values',
        'api_admin_export_zip', 'api_admin_od_reset',
        'api_config_consolidation', 'api_config_cotizacion_margen',
        'api_config_init_manual',
    ]),
    ('imports', '/api', [
        'api_import_manual_template', 'api_import_preview',
        'api_import_process',
    ]),
    ('master', '/api', [
        'api_master_filtros', 'api_master_tablas',
        'api_master_reglas_manuales', 'api_master_reprocess',
        'api_manual_columns', 'api_columns_layout',
        'api_dashboard_charts', 'api_dashboard_kpis',
        'api_master_all_columns', 'api_dashboard_filters',
        'api_master_template', 'api_master_bulk_import',
        'api_clean',
    ]),
    ('rows', '/api', [
        'api_rows_update', 'api_rows_edit_key', 'api_rows_add',
        'api_rows_delete', 'api_rows_bulk_update', 'api_rows_finalizar',
    ]),
    ('wo', '/api', [
        'api_combustible_por_wo', 'api_wo_meta', 'api_detalle_opciones',
        'api_wo_servicios', 'api_wo_historial', 'api_wo_enviar_aprobacion',
        'api_sites', 'api_wos_flm', 'api_wo_resolver',
    ]),
    ('evidencia', '/api', [
        'api_evidencia_subir', 'api_evidencia_eliminar',
        'api_evidencia_foto', 'api_evidencia_zip',
        'api_evidencia_reporte_config', 'api_evidencia_reporte_xlsx',
    ]),
    ('cotizacion', '/api', [
        'api_cotizacion_estado', 'api_cotizacion_lista',
        'api_cotizacion_registro', 'api_cotizacion_descargar_registro',
        'api_cotizacion_next_seq', 'api_cotizacion_previsualizar',
        'api_cotizacion_registro_pdf', 'api_cotizacion_registro_generar',
        'api_cotizacion_desbloquear', 'api_cotizacion_eliminar',
        'api_cotizacion_generar',
    ]),
]

def extract_function(src, fname):
    lines = src.split("\n")
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(f"def {fname}(") or line.startswith(f"def _{fname}("): # In case we renamed it or something
            start_idx = i
            break
    if start_idx == -1: return None
    
    dec_start = start_idx
    while dec_start > 0 and lines[dec_start-1].startswith("@"):
        dec_start -= 1
        
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("def ") or lines[i].startswith("class ") or lines[i].startswith("@app.route") or lines[i].startswith("# ---"):
            end_idx = i
            break
            
    return "\n".join(lines[dec_start:end_idx])


os.makedirs('blueprints', exist_ok=True)

for bp_name, prefix, funcs in BLUEPRINT_MAP:
    lines = [HEADER, f"\nbp = Blueprint('{bp_name}', __name__)\n"]
    for fname in funcs:
        chunk = extract_function(text, fname)
        if chunk:
            chunk = re.sub(r'@app\.route\b', '@bp.route', chunk)
            for f2 in funcs:
                chunk = re.sub(rf"url_for\('{f2}'", f"url_for('{bp_name}.{f2}'", chunk)
            lines.append('\n\n' + chunk.rstrip())
        else:
            lines.append(f'\n# WARNING: {fname} no encontrada en el backup\n')

    out_path = f'blueprints/{bp_name}.py'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Wrote {out_path}")
print("Done.")
