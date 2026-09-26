# -*- coding: utf-8 -*-
from services.utilidades import (
    login_required, safe_json_dumps, inject_kpis, apply_data_restrictions,
    get_session_info, get_menu_proyectos, PROYECTOS_FIJOS, PROYECTOS_REMOVIDOS,
    _parse_galones, _combustible_fecha_norm, _combustible_fecha_ord,
    _combustible_filas_gen, _combustible_chequear, _combustible_validar_gasto,
    _combustible_saldo, _flm_wo_list, _sane_data_key, _sane_dict,
    _flm_pair_ids, _flm_hermano_id, _flm_campo_propagable,
    _flm_registro_hermano, _flm_sync_campos, CAMPOS_TRABAJO_FLM
)
from services.apoyo import (
    EVIDENCIA_TIPOS, EVIDENCIA_MAX_POR_TIPO, EVIDENCIA_MAX_PEX,
    EVIDENCIA_TIPO_RESGUARDO, EVIDENCIA_MAX_RESGUARDO, EVIDENCIA_EXT_ALLOWED,
    PEX_REPORTE_XLSX, PEX_SLOTS, PEX_ANCHORS, PEX_OBS_CELLS,
    evidencia_folder, evidencia_limpiar_slot, evidencia_comprimir,
    evidencia_usa_b2, b2_cliente, evidencia_eliminar_b2,
    OD_GRAPH_BASE, OD_TOKEN_URL, _od_cuenta, _od_refresh_token_guardar,
    _od_refresh_token_actual, onedrive_access_token, _od_url,
    _onedrive_subir_a, onedrive_subir, _onedrive_eliminar_a, onedrive_eliminar,
    _evidencia_aprobacion_bloquea, _EVIDENCIA_OLD26_A_NUEVO,
    _evidencia_migrar_legacy, _evidencia_leer, _box_px, _n_a_en_box,
    _encajar_foto_cover, _pext_config, _pext_config_cajas, _pext_max,
    _fecha_larga_es, _generar_pdf_cotizacion, _generar_pdf_cotizacion_cobra,
    _obtener_registro_cotizacion, _cotizacion_registro_pdf_response
)

__all__ = [
    'login_required', 'safe_json_dumps', 'inject_kpis', 'apply_data_restrictions',
    'get_session_info', 'get_menu_proyectos', 'PROYECTOS_FIJOS', 'PROYECTOS_REMOVIDOS',
    '_parse_galones', '_combustible_fecha_norm', '_combustible_fecha_ord',
    '_combustible_filas_gen', '_combustible_chequear', '_combustible_validar_gasto',
    '_combustible_saldo', '_flm_wo_list', '_sane_data_key', '_sane_dict',
    '_flm_pair_ids', '_flm_hermano_id', '_flm_campo_propagable',
    '_flm_registro_hermano', '_flm_sync_campos', 'CAMPOS_TRABAJO_FLM',
    'EVIDENCIA_TIPOS', 'EVIDENCIA_MAX_POR_TIPO', 'EVIDENCIA_MAX_PEX',
    'EVIDENCIA_TIPO_RESGUARDO', 'EVIDENCIA_MAX_RESGUARDO', 'EVIDENCIA_EXT_ALLOWED',
    'PEX_REPORTE_XLSX', 'PEX_SLOTS', 'PEX_ANCHORS', 'PEX_OBS_CELLS',
    'evidencia_folder', 'evidencia_limpiar_slot', 'evidencia_comprimir',
    'evidencia_usa_b2', 'b2_cliente', 'evidencia_eliminar_b2',
    'OD_GRAPH_BASE', 'OD_TOKEN_URL', '_od_cuenta', '_od_refresh_token_guardar',
    '_od_refresh_token_actual', 'onedrive_access_token', '_od_url',
    '_onedrive_subir_a', 'onedrive_subir', '_onedrive_eliminar_a', 'onedrive_eliminar',
    '_evidencia_aprobacion_bloquea', '_EVIDENCIA_OLD26_A_NUEVO',
    '_evidencia_migrar_legacy', '_evidencia_leer', '_box_px', '_n_a_en_box',
    '_encajar_foto_cover', '_pext_config', '_pext_config_cajas', '_pext_max',
    '_fecha_larga_es', '_generar_pdf_cotizacion', '_generar_pdf_cotizacion_cobra',
    '_obtener_registro_cotizacion', '_cotizacion_registro_pdf_response'
]