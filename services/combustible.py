# -*- coding: utf-8 -*-
"""services/combustible.py
Reglas de saldo y normalizacion de fechas del modulo Combustible (FLM).

Vivian en `services/utilidades.py` (cajon generico) junto a helpers sin relacion;
se agruparon aqui por dominio. `services/__init__.py` las reexporta con los
mismos nombres para no cambiar ningun punto de llamada.
"""
import json
import re

from models import NucleusData


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
