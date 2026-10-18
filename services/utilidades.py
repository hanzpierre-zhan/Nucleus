# -*- coding: utf-8 -*-
"""services/utilidades.py
Funciones utilitarias y helpers compartidos por todos los blueprints.
No contiene rutas ni lógica de transporte HTTP.
"""
import json
from datetime import datetime, timedelta
from collections import Counter
from functools import wraps

from perezoso import pd
from flask import session, redirect, url_for, request, jsonify

from db import db
from models import (Proyecto, AppConfig, NucleusData, KpiConfig,
                    AccesoProyecto, HistorialCambios)

# ── Proyectos que no pueden borrarse ni accederse externamente ─────────────
PROYECTOS_FIJOS = frozenset({'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'PEXT', 'Dataper', 'Material'})
PROYECTOS_REMOVIDOS = frozenset({'FLM', 'PEXT (old)', 'Claro', 'Integratel', 'CLARO', 'INTEGRATEL', 'FLM - CLARO y INTEGRATEL'})


# ── Auth decorator ─────────────────────────────────────────────────────────
# ── Hora de Perú (UTC-5) ─────────────────────────────────────────────────
# El servidor corre en UTC: datetime.now()/utcnow() dan +5h respecto a Perú y
# después de las 7pm la FECHA salta al día siguiente. Todo lo visible al
# usuario (PDFs, listas) debe usar ahora_peru(); en BD se sigue guardando UTC.
def ahora_peru():
    """Hora actual de Perú (UTC-5) como datetime naive."""
    return datetime.utcnow() - timedelta(hours=5)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/') or '/api/' in request.path:
                return jsonify({'error': 'Tu sesión venció. Vuelve a iniciar sesión y reintenta.', 'login_required': True}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# ── JSON helpers ───────────────────────────────────────────────────────────
def safe_json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


# ── Sesión ─────────────────────────────────────────────────────────────────
def get_session_info():
    uid = session.get('user_id')
    rol = str(session.get('rol') or 'supervisor').strip().lower()
    pid_raw = session.get('current_proyecto_id')
    pid = int(pid_raw) if pid_raw else None
    return uid, rol, pid


def audit_user():
    """Usuario a registrar en campos de auditoría (X POR, GESTOR, EDITADO POR, etc.).

    En "modo silencioso" (mantenimiento), devuelve '' para no atribuir los cambios
    al administrador que está sincerando/corrigiendo información.
    """
    if session.get('silent_mode'):
        return ''
    return session.get('username') or ''


def get_menu_proyectos(user_id, user_rol):
    """Reutiliza permisos solo dentro de la solicitud actual, nunca entre usuarios."""
    from flask import request,has_request_context
    if not has_request_context():return _get_menu_proyectos(user_id,user_rol)
    cache=request.environ.setdefault('nucleus.menu_proyectos_cache',{})
    # zeno/suport ven todos los proyectos, así que el menú no depende del
    # usuario: con la clave (None, rol) se evita repetir la misma consulta una
    # vez por usuario (al listar N usuarios eran N consultas idénticas).
    key=(None,user_rol) if user_rol in ('zeno','suport') else (user_id,user_rol)
    if key not in cache:cache[key]=_get_menu_proyectos(user_id,user_rol)
    return list(cache[key])


def _get_menu_proyectos(user_id, user_rol):
    """Proyectos visibles en el menú lateral según rol."""
    if user_rol in ('zeno', 'suport'):
        return Proyecto.query.filter(Proyecto.nombre.notin_(PROYECTOS_REMOVIDOS)).order_by(Proyecto.id).all()

    accesos = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
    pids = [a.proyecto_id for a in accesos]
    proyectos = Proyecto.query.filter(Proyecto.id.in_(pids), Proyecto.nombre.notin_(PROYECTOS_REMOVIDOS)).order_by(Proyecto.id).all()
    nombres = {p.nombre for p in proyectos}
    ids_set = {p.id for p in proyectos}

    if any(n in nombres for n in ('FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'PEXT', 'Claro', 'Integratel')):
        for extra_name in ('Dataper', 'Material'):
            e = Proyecto.query.filter_by(nombre=extra_name).first()
            if e and e.id not in ids_set:
                proyectos.append(e)
                ids_set.add(e.id)

    if any(n in nombres for n in ('FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'Claro', 'Integratel')):
        extras = ('SITE', 'Generadores') if user_rol in ('gestor', 'contrata') else ('Site Name', 'Generadores', 'Combustible', 'Cotizaciones', 'SITE')
        for extra_name in extras:
            e = Proyecto.query.filter_by(nombre=extra_name).first()
            if e and e.id not in ids_set:
                proyectos.append(e)
                ids_set.add(e.id)

    return proyectos


# ── Módulo Cotizaciones ──────────────────────────────────────────────────────
def puede_cotizaciones(user_id, user_rol, proy_nombre):
    """True si el usuario puede usar el módulo Cotizaciones.

    Misma regla con la que pages.index autoriza entrar al módulo, así nadie
    pierde la descarga por fecha que ya tenía:
      · módulo abierto en la sesión,
      · rol zeno/suport/admin,
      · Cotizaciones visible en su menú (perfil/accesos),
      · acceso a FLM / FLM - ENTEL / PEXT.
    """
    if str(proy_nombre or '').strip().lower() == 'cotizaciones':
        return True
    rol = str(user_rol or '').strip().lower()
    if rol in ('zeno', 'suport', 'admin'):
        return True
    try:
        menu = get_menu_proyectos(user_id, rol) or []
    except Exception:
        menu = []
    if any(str(getattr(p, 'nombre', '') or '').strip() == 'Cotizaciones' for p in menu):
        return True
    try:
        for a in AccesoProyecto.query.filter_by(usuario_id=user_id).all():
            ap = db.session.get(Proyecto, a.proyecto_id)
            if ap and ap.nombre in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'PEXT'):
                return True
    except Exception:
        pass
    return False


def puede_rendicion(user_id, user_rol, proy_nombre):
    """True si el usuario tiene ASIGNADO el módulo Rendicion.

    Sin excepciones por rol: los botones Exportar y Sincronizar (y las acciones
    del flujo) se habilitan únicamente para quienes lo tienen asignado en su
    perfil de accesos, que es la misma lista que arma su menú lateral. Si el
    módulo ya está abierto en su sesión es porque acaba de entrar, o sea que lo
    tiene asignado.
    """
    if str(proy_nombre or '').strip().lower() == 'rendicion':
        return True
    try:
        menu = get_menu_proyectos(user_id, str(user_rol or '').strip().lower()) or []
    except Exception:
        menu = []
    return any(str(getattr(p, 'nombre', '') or '').strip().lower() == 'rendicion'
               for p in menu)


# ── KPIs ───────────────────────────────────────────────────────────────────
def inject_kpis(pid, rows, configs=None):
    if configs is None:
        configs = KpiConfig.query.filter_by(proyecto_id=pid).all()
    if not configs:
        return rows, {}

    hoy = datetime.now()
    hoy_dt = pd.to_datetime(hoy)
    dt_cache = {}
    kpi_meta = {}

    for kpi in configs:
        if kpi.tipo == 'ACUMULADO':
            cols = [c.strip() for c in kpi.col_inicio.split(',') if c.strip()]
            if not cols:
                continue
            filters = []
            try:
                if kpi.col_fin and (kpi.col_fin.startswith('[') or kpi.col_fin.startswith('{')):
                    filters = json.loads(kpi.col_fin)
                    if not isinstance(filters, list):
                        filters = []
                elif kpi.restar_contra and kpi.restar_contra != 'HOY':
                    filters = [{"col": kpi.restar_contra, "val": kpi.col_fin}]
            except Exception:
                filters = []

            combined_vals = []
            for r in rows:
                matches_all = all(
                    str(r.get(f.get('col'), '')).strip() == str(f.get('val')).strip()
                    for f in filters if f.get('col')
                )
                if matches_all:
                    vals = [str(r.get(c, '')).strip() for c in cols]
                    if all(vals):
                        combined_vals.append(" | ".join(vals))

            if combined_vals:
                counts = Counter(combined_vals)
                sorted_keys = sorted(counts.keys(), key=lambda x: counts[x], reverse=True)
                ranks = {k: i + 1 for i, k in enumerate(sorted_keys[:4])}
                kpi_meta[kpi.id] = {
                    'counts': dict(counts),
                    'ranks': ranks,
                    'max': max(counts.values()) if counts else 0,
                    'cols_involved': cols,
                    'filters': filters,
                }

        elif kpi.tipo == 'RESALTADO':
            if 'resaltadores' not in kpi_meta:
                kpi_meta['resaltadores'] = {}
            col = kpi.col_inicio
            val = kpi.col_fin
            if col not in kpi_meta['resaltadores']:
                kpi_meta['resaltadores'][col] = {}
            kpi_meta['resaltadores'][col][val] = 'hit'

    for kpi in configs:
        if kpi.tipo != 'DILACION':
            continue
        # Cache de fechas parseadas por valor distinto: las fechas se repiten
        # mucho (2500 filas -> decenas de valores únicos). pd.to_datetime es
        # caro (~0.1ms); sin cache son miles de llamadas por carga.
        for row in rows:
            val_inicio = row.get(kpi.col_inicio)
            if not val_inicio:
                row[f"KPI_{kpi.nombre}"] = None
                continue
            s_inicio = str(val_inicio).strip()
            if s_inicio in dt_cache:
                f_inicio = dt_cache[s_inicio]
            else:
                try:
                    f_inicio = pd.to_datetime(s_inicio)
                    if pd.isna(f_inicio):
                        f_inicio = None
                except Exception:
                    f_inicio = None
                dt_cache[s_inicio] = f_inicio

            if not f_inicio:
                row[f"KPI_{kpi.nombre}"] = None
                continue

            target_date = hoy_dt
            if kpi.restar_contra == 'COLUMNA' and kpi.col_fin:
                val_fin = row.get(kpi.col_fin)
                if val_fin:
                    s_fin = str(val_fin).strip()
                    if s_fin in dt_cache:
                        f_fin = dt_cache[s_fin]
                    else:
                        try:
                            f_fin = pd.to_datetime(s_fin)
                            if pd.isna(f_fin):
                                f_fin = None
                        except Exception:
                            f_fin = None
                        dt_cache[s_fin] = f_fin
                    if f_fin:
                        target_date = f_fin

            diff = target_date - f_inicio
            row[f"KPI_{kpi.nombre}"] = max(0, diff.days)

    return rows, kpi_meta


# ── Restricciones de datos ─────────────────────────────────────────────────
def apply_data_restrictions(data_list, res_obj):
    if not res_obj:
        return data_list
    parsed_res = {}
    for col, vals in res_obj.items():
        if not vals:
            continue
        parsed_res[col] = [str(v).strip().upper() for v in (vals if isinstance(vals, list) else [vals])]
    if not parsed_res:
        return data_list
    filtered = []
    for d in data_list:
        keep = True
        for col_name, allowed_vals in parsed_res.items():
            if col_name not in d:
                continue
            if str(d.get(col_name, '')).strip().upper() not in allowed_vals:
                keep = False
                break
        if keep:
            filtered.append(d)
    return filtered


# ── Helpers de datos ───────────────────────────────────────────────────────
def _sane_data_key(k):
    return str(k).replace('.', '_')


def _sane_dict(d):
    return {_sane_data_key(k): v for k, v in d.items()}
