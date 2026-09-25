import os, re

URL_MAP = {
    'login': 'auth.login',
    'logout': 'auth.logout',
    'cambiar_password': 'auth.cambiar_password',
    'switch_project': 'auth.switch_project',
    'index': 'pages.index',
    'dashboard': 'pages.dashboard',
    'configuraciones': 'pages.configuraciones',
    'admin_panel': 'pages.admin_panel',
    'proyectos_page': 'pages.proyectos_page',
    'usuarios_page': 'pages.usuarios_page',
    'healthz': 'pages.healthz',
    'mapa_site': 'pages.mapa_site',
    'api_admin_proyecto': 'admin.api_admin_proyecto',
    'api_tecnicos': 'admin.api_tecnicos',
    'api_admin_usuario': 'admin.api_admin_usuario',
    'api_admin_usuario_duplicar': 'admin.api_admin_usuario_duplicar',
    'api_admin_permisos': 'admin.api_admin_permisos',
    'api_admin_columnas': 'admin.api_admin_columnas',
    'api_column_values': 'admin.api_column_values',
    'api_admin_export_zip': 'admin.api_admin_export_zip',
    'api_admin_od_reset': 'admin.api_admin_od_reset',
    'api_config_consolidation': 'admin.api_config_consolidation',
    'api_config_cotizacion_margen': 'admin.api_config_cotizacion_margen',
    'api_config_init_manual': 'admin.api_config_init_manual',
    'api_import_manual_template': 'imports.api_import_manual_template',
    'api_import_preview': 'imports.api_import_preview',
    'api_import_process': 'imports.api_import_process',
    'api_master_filtros': 'master.api_master_filtros',
    'api_master_tablas': 'master.api_master_tablas',
    'api_master_reglas_manuales': 'master.api_master_reglas_manuales',
    'api_master_reprocess': 'master.api_master_reprocess',
    'api_manual_columns': 'master.api_manual_columns',
    'api_columns_layout': 'master.api_columns_layout',
    'api_dashboard_charts': 'master.api_dashboard_charts',
    'api_dashboard_kpis': 'master.api_dashboard_kpis',
    'api_master_all_columns': 'master.api_master_all_columns',
    'api_dashboard_filters': 'master.api_dashboard_filters',
    'api_master_template': 'master.api_master_template',
    'api_master_bulk_import': 'master.api_master_bulk_import',
    'api_clean': 'master.api_clean',
    'api_rows_update': 'rows.api_rows_update',
    'api_rows_edit_key': 'rows.api_rows_edit_key',
    'api_rows_add': 'rows.api_rows_add',
    'api_rows_delete': 'rows.api_rows_delete',
    'api_rows_bulk_update': 'rows.api_rows_bulk_update',
    'api_rows_finalizar': 'rows.api_rows_finalizar',
    'api_combustible_por_wo': 'wo.api_combustible_por_wo',
    'api_wo_meta': 'wo.api_wo_meta',
    'api_detalle_opciones': 'wo.api_detalle_opciones',
    'api_wo_servicios': 'wo.api_wo_servicios',
    'api_wo_historial': 'wo.api_wo_historial',
    'api_wo_enviar_aprobacion': 'wo.api_wo_enviar_aprobacion',
    'api_sites': 'wo.api_sites',
    'api_wos_flm': 'wo.api_wos_flm',
    'api_wo_resolver': 'wo.api_wo_resolver',
    'api_evidencia_subir': 'evidencia.api_evidencia_subir',
    'api_evidencia_eliminar': 'evidencia.api_evidencia_eliminar',
    'api_evidencia_foto': 'evidencia.api_evidencia_foto',
    'api_evidencia_zip': 'evidencia.api_evidencia_zip',
    'api_evidencia_reporte_config': 'evidencia.api_evidencia_reporte_config',
    'api_evidencia_reporte_xlsx': 'evidencia.api_evidencia_reporte_xlsx',
    'api_cotizacion_estado': 'cotizacion.api_cotizacion_estado',
    'api_cotizacion_lista': 'cotizacion.api_cotizacion_lista',
    'api_cotizacion_registro': 'cotizacion.api_cotizacion_registro',
    'api_cotizacion_descargar_registro': 'cotizacion.api_cotizacion_descargar_registro',
    'api_cotizacion_next_seq': 'cotizacion.api_cotizacion_next_seq',
    'api_cotizacion_previsualizar': 'cotizacion.api_cotizacion_previsualizar',
    'api_cotizacion_registro_pdf': 'cotizacion.api_cotizacion_registro_pdf',
    'api_cotizacion_registro_generar': 'cotizacion.api_cotizacion_registro_generar',
    'api_cotizacion_desbloquear': 'cotizacion.api_cotizacion_desbloquear',
    'api_cotizacion_eliminar': 'cotizacion.api_cotizacion_eliminar',
    'api_cotizacion_generar': 'cotizacion.api_cotizacion_generar',
}

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    changed = False
    
    # Python files url_for('xxx'
    if filepath.endswith('.py'):
        for old, new in URL_MAP.items():
            # match url_for('old') or url_for("old") 
            # make sure it is not already 'pages.index' etc.
            pattern = rf"url_for\((['\"]){old}(['\"])"
            def repl(m):
                return f"url_for({m.group(1)}{new}{m.group(2)}"
            
            new_content = re.sub(pattern, repl, content)
            if new_content != content:
                content = new_content
                changed = True
                
    # HTML files url_for('xxx'
    elif filepath.endswith('.html'):
        for old, new in URL_MAP.items():
            pattern = rf"url_for\((['\"]){old}(['\"])"
            def repl(m):
                return f"url_for({m.group(1)}{new}{m.group(2)}"
            
            new_content = re.sub(pattern, repl, content)
            if new_content != content:
                content = new_content
                changed = True

    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed {filepath}")

# Fix blueprints
import glob
for f in glob.glob('blueprints/*.py'):
    fix_file(f)

# Fix templates
for root, dirs, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            fix_file(os.path.join(root, file))

# Fix services
for f in glob.glob('services/*.py'):
    fix_file(f)
