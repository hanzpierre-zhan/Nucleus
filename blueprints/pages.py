# -*- coding: utf-8 -*-
import os, io, re, json, time, glob, zipfile, gzip, mimetypes, tempfile
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timedelta
from collections import Counter
from types import SimpleNamespace
from flask import (Blueprint, request, jsonify, session, redirect, url_for,
                   render_template, current_app, make_response,
                   send_from_directory, send_file, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from perezoso import pd
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
from services import (
    login_required,
    inject_kpis,
    apply_data_restrictions,
    get_session_info,
    get_menu_proyectos,
    puede_cotizaciones,
    puede_rendicion,
    _combustible_fecha_ord,
    _flm_wo_list,
)
from services.recursos_flm import contexto_recursos, filtrar_catalogo, FLM_NOMBRES


bp = Blueprint('pages', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Cache del cruce Site Name → FLM (5.000+ filas con json.loads en CADA / de FLM)
# ─────────────────────────────────────────────────────────────────────────────
_MARCADOR_DATOS_TABLA = '__NUCLEUS_DATOS_TABLA_9f4c1a__'
_SITE_MAP_TTL = 120.0
_site_map_cache = {'ts': 0.0, 'data': None}


def invalidar_site_map_cache():
    _site_map_cache['ts'] = 0.0
    _site_map_cache['data'] = None


def _get_site_map():
    from services.alcance_proyectos import contexto
    alcance = contexto()
    clave_alcance = tuple(sorted(alcance['familias'])) if alcance is not None else None
    if _site_map_cache.get('alcance') == clave_alcance and _site_map_cache['data'] is not None and (time.time() - _site_map_cache['ts']) < _SITE_MAP_TTL:
        return _site_map_cache['data']
    site_map = {}
    site_proy = Proyecto.query.filter_by(nombre='Site Name').first()
    if site_proy:
        for sr in NucleusData.query.filter_by(proyecto_id=site_proy.id).all():
            try:
                sd = json.loads(sr.data_json)
            except Exception:
                continue
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
    _site_map_cache['data'] = site_map
    _site_map_cache['alcance'] = clave_alcance
    _site_map_cache['ts'] = time.time()
    return site_map



@bp.route('/')
@login_required
def index():
    user_id, user_rol, pid = get_session_info()
    is_admin = user_rol == 'zeno'
    is_privileged = user_rol == 'zeno'

    if session.get('current_proyecto_nombre') == 'FLM - CLARO y INTEGRATEL':
        proyectos_activos = get_menu_proyectos(user_id, user_rol)
        if proyectos_activos:
            proyecto_activo = proyectos_activos[0]
            session['current_proyecto_id'] = proyecto_activo.id
            session['current_proyecto_nombre'] = proyecto_activo.nombre
            return redirect(url_for('pages.index'))
        session.clear()
        return redirect(url_for('auth.login'))

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
        if not acc and contexto_recursos() and any(p.id == pid for p in get_menu_proyectos(user_id, user_rol)):
            acc = SimpleNamespace(restricciones='{}')
        if not acc:
            # Dataper/Material: permitir si el usuario tiene FLM o PEXT asignado.
            # Site Name: permitir solo si el usuario tiene FLM asignado.
            proy_check = db.session.get(Proyecto, pid)
            if proy_check and proy_check.nombre in ('Dataper', 'Material'):
                accs = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
                allowed = False
                for a in accs:
                    ap = db.session.get(Proyecto, a.proyecto_id)
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'PEXT'):
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
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT'):
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
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT'):
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
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT'):
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
                    if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'PEXT'):
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

    # Se leen todas las claves de configuración del proyecto en UNA consulta y
    # se sirven desde memoria: en Render/Neon cada ida y vuelta a la BD se paga.
    app_cfg = {c.clave: c for c in AppConfig.query.filter_by(proyecto_id=pid).all()}
    schema_config = app_cfg.get('app_schema')
    columns_set = set(json.loads(schema_config.valor)) if schema_config else set()

    manual_cfg = app_cfg.get('manual_columns')
    manual_cols_data = json.loads(manual_cfg.valor) if manual_cfg else []
    from services.alcance_proyectos import limitar_opciones
    manual_cols_data = limitar_opciones(manual_cols_data)
    from services.legacy_columns import retired
    manual_cols_data=[c for c in manual_cols_data if not retired(c.get('nombre'))]
    columns_set={c for c in columns_set if not retired(c)}
    for mc in manual_cols_data:
        columns_set.add(mc['nombre'])

    # Generadores: el campo TECNICO ASIGNADO se llena dinámicamente con los técnicos
    # activos de Dataper con PROYECTO=FLM/PEXT/Claro/Integratel (catálogo declarado por el admin).
    # Combustible: QR ASIGNADO lista los QR declarados en Generadores, TIPO se
    # autocompleta desde el mapa generador->TIPO, TECNICO ASIGNADO lista los técnicos.
    proy_actual = db.session.get(Proyecto, pid)
    proy_actual_nombre = proy_actual.nombre.strip() if proy_actual and proy_actual.nombre else ''
    if proy_actual_nombre == 'Dataper':
        from services.personal import configurar
        manual_cols_data = configurar(manual_cols_data)
        columns_set.update(c['nombre'] for c in manual_cols_data)
    if proy_actual_nombre in ('Material','SITE','Generadores'):
        from services.proyectos_catalogo import configurar as configurar_proyectos
        manual_cols_data = configurar_proyectos(manual_cols_data)
        columns_set.update(c['nombre'] for c in manual_cols_data)
    if proy_actual_nombre == 'Cotizaciones':
        columns_set.update(('ADJUNTO CORREO CLIENTE', 'NOMBRE CORREO CLIENTE',
                            'ADJUNTO COTIZACION PROVEEDOR', 'ADJUNTO FACTURA PROVEEDOR'))
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
                # Excluir solo si ESTADO tiene un valor distinto a ACTIVO
                if est and est != 'ACTIVO':
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
    
    # Campo del formulario: debe existir en la tabla aunque el esquema importado sea antiguo.
    if proy_actual_nombre.strip().lower() == 'cotizaciones':
        columns_set.add('TIPO DE GASTO')
        columns_set.add('TIPO GASTO APROBACION')

    # Add KPI columns to the set so frontend can see them
    kpi_configs = KpiConfig.query.filter_by(proyecto_id=pid).all()
    for k in kpi_configs:
        if k.tipo == 'DILACION':
            columns_set.add(f"KPI_{k.nombre}")
    
    # Ocultar columnas internas (prefijo _) y redundantes de la vista
    columns_set = {c for c in columns_set if not c.startswith('_') and c != 'WO Number'}
    # FLM/PEXT: EDITADO POR se reemplaza por GESTOR (quien presiona Guardar, el admin no cuenta).
    if proy_actual_nombre in ('FLM', 'FLM - ENTEL', 'PEXT', 'FLM - PEXT'):
        columns_set.discard('EDITADO POR')
        columns_set.add('GESTOR')
    # Columna obsoleta que no aporta información (FLM/PEXT).
    for _hc in list(columns_set):
        if 'HORA DE CR' in _hc.upper():
            columns_set.discard(_hc)
    
    personal_rendicion = None
    if proy_actual_nombre.strip().lower() == 'rendicion':
        columns_set.update(('N° COTIZACION', 'ENVIADO A TRANSITO POR', 'FECHA ENVIO TRANSITO'))
        from services.rendicion_personal import indice_personal, completar_personal
        personal_rendicion = indice_personal()
        columns_set.add('DEPARTAMENTO')
        columns_set.discard('VERIFICACIÓN PERSONAL')
        # Cruce de personal: columnas de auditoría (nombre ingresado vs cruce con Dataper).
        columns_set.add('Técnico beneficiario (Form)')
        columns_set.add('Documento del beneficiario (Form)')
        columns_set.add('Cruce de personal')

    # Load and Filter data
    from services.columnas_fuente import presentar as presentar_columnas_fuente
    if proy_actual_nombre == 'Dataper':
        from services.personal import presentar as presentar_personal
    if proy_actual_nombre in ('Material', 'SITE', 'Generadores'):
        from services.proyectos_catalogo import presentar as presentar_proyecto

    # Solo se necesitan key_value + data_json: pedir esas dos columnas evita
    # cargar entidades ORM completas (menos memoria y menos sobrecarga en
    # proyectos con miles de filas).
    filas = db.session.query(
        NucleusData.key_value, NucleusData.data_json
    ).filter_by(proyecto_id=pid).all()
    raw_data = []
    for key_value, data_json in filas:
        d = json.loads(data_json)
        if personal_rendicion is not None:
            completar_personal(d, personal_rendicion)
        d = presentar_columnas_fuente(d, proy_actual_nombre, key_value)
        if proy_actual_nombre == 'Dataper':
            d = presentar_personal(d)
        if proy_actual_nombre in ('Material','SITE','Generadores'):
            d = presentar_proyecto(d)
        d['_key'] = key_value
        if proy_actual_nombre in ('FLM', 'FLM - ENTEL', 'PEXT', 'FLM - PEXT') and not d.get('GESTOR'):
            d['GESTOR'] = d.get('EDITADO POR') or d.get('_ultimo_usuario_manual') or ''
            
        wo_val = str(d.get('NUMERO DE WO') or d.get('WO NUMBER') or d.get('WO Number') or d.get('Número de WO') or '').strip()
        if wo_val:
            prefix = wo_val.split('-')[0]
            if prefix and prefix[0].isalpha():
                d['Tipo WO'] = prefix
                columns_set.add('Tipo WO')

        raw_data.append(d)

    # Las filas crudas ya están decodificadas: se liberan antes de transformar y
    # serializar para no mantener a la vez los JSON de origen y los dicts.
    del filas

    # Dataper y Material: solo mostrar registros cuyo campo PROYECTO sea FLM/PEXT/Claro/Integratel
    # según los proyectos asignados al usuario (si tiene varios, muestra todos). Comparación case-insensitive.
    if proy_actual_nombre in ('Dataper', 'Material'):
        raw_data = filtrar_catalogo(raw_data)
        contexto = contexto_recursos()
        if contexto:
            for columna in manual_cols_data:
                if columna.get('nombre') == 'PROYECTO':
                    columna['opciones'] = [contexto['flm_nombre']]

    # Cruce dinámico: Site Name → FLM. Se agregan a cada fila de FLM las columnas
    # DIRECCION, LATITUD, LONGITUD tomadas del proyecto "Site Name" cruzando por
    # la columna "Nombre de Site" ↔ "NOMBRE DE SITE", solo registros ACTIVOS.
    if proy_actual_nombre in ('FLM', 'FLM - ENTEL'):
        site_proy = Proyecto.query.filter_by(nombre='Site Name').first()
        if site_proy:
            site_map = _get_site_map()
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

    data, kpi_meta = inject_kpis(pid, data, kpi_configs)

    config_key = app_cfg.get('primary_key')
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
    # Si es Cotizaciones o Combustible y NO hay layout guardado, crearlo una
    # sola vez con el orden por defecto (N° ORDEN primero). Un layout existente
    # NUNCA se reescribe aquí: el orden y la visibilidad que configuró el admin
    # con "Ordenar columnas" mandan y no deben cambiar en cada carga.
    _proj_nombre_for_layout = proy_actual_nombre.lower()
    if _proj_nombre_for_layout in ('cotizaciones', 'combustible') and 'N° ORDEN' in cols:
        try:
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

    # Layout de columnas definido por el admin (orden + visibilidad) para todos los usuarios.
    layout_cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='column_layout').first()
    column_layout = json.loads(layout_cfg.valor) if layout_cfg and layout_cfg.valor else []
    # En Rendicion cada hoja guarda su propia vista: column_layout__depositos, etc.
    column_layout_vistas = {}
    try:
        _pref = 'column_layout__'
        for _clave, _vcfg in app_cfg.items():
            if _clave and _clave.startswith(_pref):
                _vista = _clave[len(_pref):].strip().lower()
                if _vista and _vcfg.valor:
                    column_layout_vistas[_vista] = json.loads(_vcfg.valor)
    except Exception:
        column_layout_vistas = {}

    # List allowed projects for the menu
    proyectos = get_menu_proyectos(user_id, user_rol)
    # Descarga de Cotizaciones por fecha: disponible a quien tenga el módulo.
    puede_coti = puede_cotizaciones(user_id, user_rol, session.get('current_proyecto_nombre'))
    # Exportar / Sincronizar y botones del flujo: para quien tenga Rendicion.
    puede_rend = puede_rendicion(user_id, user_rol, session.get('current_proyecto_nombre'))

    # El HTML solo necesita el TEXTO del JSON. Se serializa aquí y se inserta
    # con un marcador único en vez de pasar el string gigante a Jinja: si se
    # pasa como valor, Jinja lo copia varias veces al renderizar (para ~8 MB de
    # datos el pico subía a ~50 MB). Además se liberan los diccionarios antes
    # de renderizar. El HTML resultante es byte a byte el mismo.
    datos_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    # Liberar las estructuras pesadas (dicts decodificados) antes de renderizar:
    # el HTML solo necesita `datos_json`.
    del data, raw_data

    html = render_template('index.html', 
                          data=_MARCADOR_DATOS_TABLA, 
                          columns=json.dumps(cols), 
                          pk=pk, 
                          manual_cols=json.dumps(manual_cols_data),
                          column_layout=json.dumps(column_layout),
                          column_layout_vistas=json.dumps(column_layout_vistas),
                          kpi_meta=json.dumps(kpi_meta),
                          changed_keys=json.dumps(changed_keys),
                          gen_tipo_map=json.dumps(gen_tipo_map),
                          gen_tecnico_map=json.dumps(gen_tecnico_map),
                          gen_zona_map=json.dumps(gen_zona_map),
                          gen_saldo_map=json.dumps(gen_saldo_map),
                          wo_list=json.dumps(wo_list),
                          proyecto_id=pid,
                          proyectos_list=proyectos,
                          puede_cotizaciones=puede_coti,
                          puede_rendicion=puede_rend)

    return html.replace(_MARCADOR_DATOS_TABLA, datos_json)


@bp.route('/dashboard')
@login_required
def dashboard():
    # Módulo Dashboard sustituido por Analytics (igual que en Anton).
    return redirect(url_for('pages.analytics'))

@bp.route('/analytics')
@login_required
def analytics():
    """Dashboard de FLM - ENTEL, independiente del módulo de procedencia."""
    user_id, user_rol, pid = get_session_info()
    proyectos = get_menu_proyectos(user_id, user_rol)
    proy = next((p for p in proyectos if p.nombre.strip().upper() == 'FLM - ENTEL'), None)
    if user_rol in ('contrata', 'gestor') or proy is None:
        return redirect(url_for('pages.index'))
    restricciones = {}
    if user_rol != 'zeno':
        acceso = AccesoProyecto.query.filter_by(usuario_id=user_id, proyecto_id=proy.id).first()
        if not acceso:
            return redirect(url_for('pages.index'))
        try:
            restricciones = json.loads(acceso.restricciones or '{}')
        except (ValueError, TypeError):
            restricciones = {}
    from services.dashboard_integratel import indicadores
    def registros():
        for fila in NucleusData.query.with_entities(NucleusData.key_value, NucleusData.data_json).filter_by(proyecto_id=proy.id).order_by(NucleusData.id).yield_per(500):
            try:
                datos = json.loads(fila.data_json)
            except (ValueError, TypeError):
                continue
            if isinstance(datos, dict):
                datos['_key'] = fila.key_value
                if apply_data_restrictions([datos], restricciones):
                    yield datos
    dashboard = indicadores(registros())
    return render_template('dashboard_integratel.html', dashboard=dashboard,
                           proyectos_list=proyectos, proyecto_nombre=proy.nombre,
                           proyecto_id=proy.id, data_total=dashboard['total'], data_limite=dashboard['total'])


@bp.route('/analytics/cotizaciones')
@login_required
def analytics_cotizaciones():
    """Dashboard comercial de Cotizaciones: cantidad y plata por pestaña,
    quién generó/solicitó cada cotización y avance de archivos de proveedor.
    Vista separada: el dashboard operativo (/analytics) no cambia."""
    user_id, user_rol, pid = get_session_info()
    proyectos = get_menu_proyectos(user_id, user_rol)
    # Analytics es una vista global: se muestra la data completa del módulo a
    # todos los usuarios, sin recortar por el proyecto/perfil con el que entró.
    proy = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if proy is None:
        proy = next((p for p in proyectos if str(p.nombre).strip().lower() == 'cotizaciones'), None)
    if proy is None:
        return redirect(url_for('pages.analytics'))
    from services.alcance_proyectos import vista_global
    from services.dashboard_cotizaciones import indicadores
    def registros():
        for fila in NucleusData.query.filter_by(proyecto_id=proy.id).order_by(NucleusData.id).yield_per(500):
            try:
                datos = json.loads(fila.data_json)
            except (ValueError, TypeError):
                continue
            if isinstance(datos, dict):
                datos['_key'] = fila.key_value
                yield datos
    with vista_global():
        dashboard = indicadores(registros())
    return render_template('dashboard_cotizaciones.html', dashboard=dashboard,
                           proyectos_list=proyectos, proyecto_nombre='Cotizaciones',
                           proyecto_id=proy.id, data_total=dashboard['total'], data_limite=dashboard['total'])


@bp.route('/analytics/rendicion')
@login_required
def analytics_rendicion():
    """Dashboard de Caja Chica (flujo de Rendición): dónde se queda cada caso,
    cantidad y plata por pestaña. Vista separada: no altera el dashboard
    operativo."""
    user_id, user_rol, pid = get_session_info()
    proyectos = get_menu_proyectos(user_id, user_rol)
    # Analytics es una vista global: la data del módulo se muestra completa para
    # todos los usuarios, independientemente del proyecto/perfil de origen.
    proy = Proyecto.query.filter_by(nombre='Rendicion').first()
    if proy is None:
        proy = next((p for p in proyectos if str(p.nombre).strip().lower() == 'rendicion'), None)
    if proy is None:
        return redirect(url_for('pages.analytics'))
    from services.alcance_proyectos import vista_global
    from services.dashboard_rendicion import indicadores
    def registros():
        for fila in NucleusData.query.filter_by(proyecto_id=proy.id).order_by(NucleusData.id).yield_per(500):
            try:
                datos = json.loads(fila.data_json)
            except (ValueError, TypeError):
                continue
            if isinstance(datos, dict):
                datos['_key'] = fila.key_value
                yield datos
    with vista_global():
        dashboard = indicadores(registros())
    return render_template('dashboard_rendicion.html', dashboard=dashboard,
                           proyectos_list=proyectos, proyecto_nombre='Rendicion',
                           proyecto_id=proy.id, data_total=dashboard['total'], data_limite=dashboard['total'])


@bp.route('/analytics/cobranza')
@login_required
def analytics_cobranza():
    """Cuadro de control de cobranza: cuánto se cobrará y cuánto está pendiente.

    Reutiliza el catálogo ya consolidado por el módulo Refacturable (una fila
    por cotización aprobada, cruzada con los FLM y el seguimiento manual), así
    no se duplica el cruce WO→cliente ni la lectura de RefacturableDetalle."""
    user_id, user_rol, pid = get_session_info()
    proyectos = get_menu_proyectos(user_id, user_rol)
    if not puede_cotizaciones(user_id, user_rol, session.get('current_proyecto_nombre')):
        return redirect(url_for('pages.analytics'))
    from blueprints.refacturable import _registros
    from services.dashboard_cobranza import indicadores
    dashboard = indicadores(_registros())
    return render_template('dashboard_cobranza.html', dashboard=dashboard,
                           proyectos_list=proyectos, proyecto_nombre='Cobranza',
                           proyecto_id=None, data_total=dashboard['total'], data_limite=dashboard['total'])


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
    from services.usuarios import usuarios_activos
    user = usuarios_activos().all()
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
    if user_rol != 'zeno':
        # Debe tener FLM para ver el mapa de sites
        has_flm = any(p.nombre in FLM_NOMBRES or p.id == proy_site.id for p in get_menu_proyectos(user_id, user_rol))
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


# ─────────────────────────────────────────────────────────────────────────────
# Avisos legales (públicos: se enlazan desde el login y desde el banner de cookies)
# ─────────────────────────────────────────────────────────────────────────────
@bp.route('/privacidad')
def privacidad_page():
    return render_template('legal.html', seccion='privacidad')


@bp.route('/terminos')
def terminos_page():
    return render_template('legal.html', seccion='terminos')


@bp.route('/cookies')
def cookies_page():
    return render_template('legal.html', seccion='cookies')
