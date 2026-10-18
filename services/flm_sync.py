# -*- coding: utf-8 -*-
"""services/flm_sync.py
Sincronizacion de campos de trabajo entre FLM y su proyecto hermano (por CM).

Vivian en `services/utilidades.py`. `services/__init__.py` las reexporta con los
mismos nombres; aqui quedan junto a lo unico que las usa (el flujo de WO/filas).
"""
import json

from models import Proyecto, NucleusData
from services.utilidades import safe_json_dumps


def _flm_wo_list():
    """Lista de WOs (CM) declarados en FLM - ENTEL, para el buscador de Combustible."""
    try:
        flm_proy = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
        if not flm_proy:
            return []
        wo_set = set()
        wo_key = None
        # Un solo recorrido: husmear la columna WO en las primeras filas y
        # recolectar en el mismo pass (antes eran 2 full-scans de FLM).
        all_rows = NucleusData.query.filter_by(proyecto_id=flm_proy.id).all()
        for r in all_rows:
            if wo_key:
                break
            try:
                d = json.loads(r.data_json)
            except Exception:
                continue
            for k in d.keys():
                if ('WO' in k.upper() and 'NUMBER' in k.upper()) or k in ('Número de WO', 'Numero de WO'):
                    wo_key = k
                    break
        for r in all_rows:
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

def _flm_pair_ids():
    """Devuelve (id_flm_entel, None) — solo existe un proyecto FLM (renombrado a FLM - ENTEL).
    Retorna (None, None) si no se encuentra el proyecto."""
    try:
        flm = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
        if flm:
            return flm.id, None
        return None, None
    except Exception:
        return None, None


def _flm_hermano_id(pid):
    """Si pid es FLM - ENTEL, devuelve None (no hay hermano); si no, None."""
    # FLM - ENTEL es el único proyecto FLM, no tiene hermano espejo.
    # Esta función se mantiene por compatibilidad con el resto del código.
    return None



# ── Sync FLM <-> FLM - ENTEL por CM ────────────────────────────────────────
# FLM - ENTEL comparte códigos de CM. Como el esquema de columnas de cada
# proyecto es DISTINTO, la sincronización NO copia todo el registro: solo
# propaga al proyecto hermano los campos de trabajo que el usuario edita
# (modal WO, evidencia/fotos, estado), evitando pisar columnas propias de
# cada esquema.
CAMPOS_TRABAJO_FLM = frozenset({
    'SERVICIO', 'CIUDAD', 'TECNICO ASIGNADO', 'CONTRATA', 'MOTIVO DE AVERÍA',
    'SISTEMAS', 'MATERIALES', 'INICIO DE PARADA', 'FIN DE PARADA', 'BITACORA',
    'INICIO EJECUCION', 'FIN EJECUCION',
    'SOLUCIÓN', 'LATITUD', 'LONGITUD', 'SE INSTALÓ MUFAS', 'LATITUD MUFAS',
    'LONGITUD MUFAS', 'COTIZACION_ITEMS', 'COTIZACION_NOTA', 'COTIZACION_NUMERO',
    'REQUIERE CORRECTIVO FINAL', 'DETALLE CORRECTIVO', 'GESTOR', 'EDITADO POR',
    'Estado de la tarea (WO State)', 'FECHA CAMBIO ESTADO', '_ENVIADO_APROBACION',
    'REQUIERE BIÁTICOS', 'MONTO BIÁTICOS (SOLES)', 'COSTO DE MATERIAL (SOLES)',
})


def _flm_campo_propagable(campo, data_hermano):
    """Un campo editado se propaga al hermano si es de trabajo (modal/evidencia)
    o si el proyecto hermano ya tiene esa columna."""
    return (campo.startswith('_') or campo in CAMPOS_TRABAJO_FLM
            or campo in data_hermano)


def _flm_registro_hermano(pid, key):
    """Registro NucleusData del mismo CM en el proyecto hermano FLM/FLM (old),
    o None."""
    her = _flm_hermano_id(pid)
    if her is None:
        return None
    return NucleusData.query.filter_by(proyecto_id=her, key_value=str(key)).first()


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
