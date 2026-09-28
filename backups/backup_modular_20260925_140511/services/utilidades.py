# -*- coding: utf-8 -*-
"""services/utilidades.py
Funciones utilitarias y helpers compartidos por todos los blueprints.
No contiene rutas ni lógica de transporte HTTP.
"""
import json
import re
from datetime import datetime
from collections import Counter
from functools import wraps

import pandas as pd
from flask import session, redirect, url_for

from db import db
from models import (Proyecto, AppConfig, NucleusData, KpiConfig,
                    AccesoProyecto, HistorialCambios)

# ── Proyectos que no pueden borrarse ni accederse externamente ─────────────
PROYECTOS_FIJOS = frozenset({'FLM - ENTEL', 'PEXT', 'Dataper', 'Material'})
PROYECTOS_REMOVIDOS = frozenset({'FLM', 'PEXT (old)', 'Claro', 'Integratel'})


# ── Auth decorator ─────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
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


def get_menu_proyectos(user_id, user_rol):
    """Proyectos visibles en el menú lateral según rol."""
    if user_rol in ('gestor', 'contrata'):
        accesos = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
        pids = [a.proyecto_id for a in accesos]
        return Proyecto.query.filter(Proyecto.id.in_(pids)).order_by(Proyecto.id).all()

    if user_rol in ('zeno', 'suport'):
        return Proyecto.query.order_by(Proyecto.id).all()

    accesos = AccesoProyecto.query.filter_by(usuario_id=user_id).all()
    pids = [a.proyecto_id for a in accesos]
    proyectos = Proyecto.query.filter(Proyecto.id.in_(pids)).order_by(Proyecto.id).all()
    nombres = {p.nombre for p in proyectos}
    ids_set = {p.id for p in proyectos}

    if any(n in nombres for n in ('FLM - ENTEL', 'PEXT', 'Claro', 'Integratel')):
        for extra_name in ('Dataper', 'Material'):
            e = Proyecto.query.filter_by(nombre=extra_name).first()
            if e and e.id not in ids_set:
                proyectos.append(e)
                ids_set.add(e.id)

    if any(n in nombres for n in ('FLM - ENTEL', 'Claro', 'Integratel')):
        for extra_name in ('Site Name', 'Generadores', 'Combustible', 'Cotizaciones', 'SITE'):
            e = Proyecto.query.filter_by(nombre=extra_name).first()
            if e and e.id not in ids_set:
                proyectos.append(e)
                ids_set.add(e.id)

    return proyectos


# ── KPIs ───────────────────────────────────────────────────────────────────
def inject_kpis(pid, rows):
    configs = KpiConfig.query.filter_by(proyecto_id=pid).all()
    if not configs:
        return rows, {}

    hoy = datetime.now()
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
        for row in rows:
            val_inicio = row.get(kpi.col_inicio)
            if not val_inicio:
                row[f"KPI_{kpi.nombre}"] = None
                continue
            try:
                f_inicio = pd.to_datetime(str(val_inicio).strip())
                if pd.isna(f_inicio):
                    f_inicio = None
            except Exception:
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
                    except Exception:
                        pass

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


# ── Combustible helpers ────────────────────────────────────────────────────
def _parse_galones(n):
    try:
        return float(str(n or '').replace(',', '.').strip())
    except (ValueError, TypeError):
        return 0.0


def _combustible_fecha_norm(v):
    s = str(v or '').strip().replace('T', ' ')
    if not s:
        return ''
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ ](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$', s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} {(m.group(4) or '00').zfill(2)}:{(m.group(5) or '00').zfill(2)}"
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ ](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$', s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)} {(m.group(4) or '00').zfill(2)}:{(m.group(5) or '00').zfill(2)}"
    return s


def _combustible_fecha_ord(v):
    s = _combustible_fecha_norm(v)
    if s.endswith(' 00:00'):
        s = s[:-6] + ' 23:59'
    return s


def _combustible_filas_gen(pid, generador):
    filas = []
    try:
        for r in NucleusData.query.filter_by(proyecto_id=pid).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            if str(d.get('QR ASIGNADO', '')).strip() != generador:
                continue
            filas.append({
                'key': r.key_value,
                'fecha': _combustible_fecha_norm(d.get('FECHA', '')),
                'mov': str(d.get('MOVIMIENTO', '')).strip().upper(),
                'gal': _parse_galones(d.get('GALONES')),
            })
    except Exception:
        pass
    filas.sort(key=lambda f: (_combustible_fecha_ord(f['fecha']), str(f.get('key') or '')))
    return filas


def _combustible_chequear(filas):
    bal = 0.0
    for f in filas:
        bal = bal + f['gal'] if f['mov'] != 'GASTO' else bal - f['gal']
        if bal < -1e-9:
            return False, {'key': f.get('key'), 'fecha': f.get('fecha'), 'saldo': round(bal, 2)}
    return True, {'saldo_final': round(bal, 2)}


def _combustible_validar_gasto(pid, generador, fecha, galones, excluir_key=None):
    filas = _combustible_filas_gen(pid, generador)
    if excluir_key is not None:
        filas = [f for f in filas if str(f.get('key')) != str(excluir_key)]
    filas.append({'key': '(nuevo)', 'fecha': _combustible_fecha_norm(fecha),
                  'mov': 'GASTO', 'gal': float(galones)})
    filas.sort(key=lambda f: (_combustible_fecha_ord(f['fecha']), str(f.get('key') or '')))
    ok, info = _combustible_chequear(filas)
    if ok:
        return True, info.get('saldo_final', 0.0)
    return False, info


def _combustible_saldo(pid, generador):
    filas = _combustible_filas_gen(pid, generador)
    ok, info = _combustible_chequear(filas)
    return info.get('saldo_final', 0.0)


def _flm_wo_list():
    """Lista de WOs (CM) declarados en FLM - ENTEL, para el buscador de Combustible."""
    try:
        flm_proy = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
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
                if ('WO' in k.upper() and 'NUMBER' in k.upper()) or k in ('Número de WO', 'Numero de WO'):
                    wo_key = k
                    break
            if wo_key:
                break
        for r in NucleusData.query.filter_by(proyecto_id=flm_proy.id).all():
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            if wo_key:
                wo = str(d.get(wo_key, '')).strip()
                if wo:
                    wo_set.add(wo)
            else:
                for k, v in d.items():
                    if 'WO' in str(k).upper():
                        w = str(v).strip()
                        if w:
                            wo_set.add(w)
        return sorted(wo_set)
    except Exception:
        return []

def _flm_hermano_id(pid):
    """Si pid es FLM o FLM - ENTEL, devuelve el id del proyecto hermano; si no, None."""
    a, b = _flm_pair_ids()
    if a is None or b is None:
        return None
    if pid == a:
        return b
    if pid == b:
        return a
    return None


def _flm_sync_campos(pid, key, campos, metadatos):
    """Propaga {campo: valor} al registro hermano del mismo CM. Solo los campos
    propagables (ver _flm_campo_propagable). `metadatos` son campos fijos que se
    aplican siempre (usuario/edición/estado)."""
    her = _flm_hermano_id(pid)
    if her is None:
        return
    rec = _flm_registro_hermano(pid, key)
    if rec is None:
        return
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    cambio = False
    for campo, valor in campos.items():
        if not _flm_campo_propagable(campo, d):
            continue
        d[campo] = valor
        cambio = True
    for k, v in (metadatos or {}).items():
        if v is not None and d.get(k) != v:
            d[k] = v
            cambio = True
    if cambio:
        rec.data_json = safe_json_dumps(d)


