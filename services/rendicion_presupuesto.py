"""Nombres canónicos de presupuesto de Rendición, sin alterar otros campos."""
import json
import re
import unicodedata
from sqlalchemy import event, select
from db import db
from models import NucleusData, Proyecto, AppConfig


def _normalizar(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower())


def presupuesto(value):
    return {'gastocobra':'GASTO COBRA', 'costocobra':'GASTO COBRA',
            'refacturable':'REFACTURABLE', 'refracturable':'REFACTURABLE'}.get(_normalizar(value), value)


def corregir_fila(data):
    if not isinstance(data, dict):
        return False
    changed = False
    for key, value in list(data.items()):
        if _normalizar(key) == 'tipodepresupuesto':
            fixed = presupuesto(value)
            if fixed != value:
                data[key] = fixed
                changed = True
    return changed


def corregir_opciones(config):
    if not isinstance(config, list):
        return False
    changed = False
    for column in config:
        if not isinstance(column, dict) or _normalizar(column.get('nombre')) != 'tipodepresupuesto':
            continue
        options = column.get('opciones')
        if not isinstance(options, list):
            continue
        fixed = list(dict.fromkeys(presupuesto(v) for v in options))
        if fixed != options:
            column['opciones'] = fixed
            changed = True
    return changed


def instalar():
    if getattr(instalar, 'ready', False):
        return

    @event.listens_for(db.session, 'before_flush')
    def normalizar_escrituras(session, *_):
        candidates = [r for r in list(session.new)+list(session.dirty)
                      if isinstance(r, NucleusData) or isinstance(r, AppConfig) and r.clave == 'manual_columns']
        if not candidates:
            return
        ids = set(session.connection().execute(select(Proyecto.id).where(Proyecto.nombre == 'Rendicion')).scalars())
        for row in candidates:
            if row.proyecto_id not in ids:
                continue
            raw = row.data_json if isinstance(row, NucleusData) else row.valor
            try:
                data = json.loads(raw or '{}')
            except (ValueError, TypeError):
                continue
            changed = corregir_fila(data) if isinstance(row, NucleusData) else corregir_opciones(data)
            if changed:
                fixed = json.dumps(data, ensure_ascii=False)
                if isinstance(row, NucleusData):
                    row.data_json = fixed
                else:
                    row.valor = fixed
    instalar.ready = True
