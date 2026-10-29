"""Reserva transaccional de la secuencia compartida de Cotizaciones."""
import json
import re

from db import db
from models import AppConfig, NucleusData

NUMERO = re.compile(r'^(?:HW|EN|CL|IN|PX)-(\d{4})-(?:(?:0[1-9]|1[0-2])-)?(\d{6,7})(?:\.\d+)?$')


def _entero(valor, defecto=0):
    return int(valor) if str(valor or '').isdigit() else defecto


def limites(pid, year):
    """Incluye claves históricas y excepciones recuperadas, de todos los clientes."""
    max_numero, max_orden = 29, 0
    for key, raw in db.session.query(NucleusData.key_value, NucleusData.data_json).filter_by(proyecto_id=pid):
        try:
            datos = json.loads(raw)
        except (ValueError, TypeError):
            datos = {}
        for valor in (key, datos.get('N° COTIZACION')):
            match = NUMERO.fullmatch(str(valor or '').strip())
            if match and int(match[1]) == int(year):
                max_numero = max(max_numero, int(match[2]))
        # Los sufijos históricos no consumen ni reinician el contador normal.
        orden = str(datos.get('N° ORDEN') or '').split('.')[0]
        max_orden = max(max_orden, _entero(orden))
    return max_numero + 1, max_orden + 1


def bloquear_config(pid):
    """La fila existe antes del FOR UPDATE, incluso en la primera alta concurrente."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    db.session.execute(insert(AppConfig).values(
        proyecto_id=pid, clave='cotizacion_next_seq', valor='30'
    ).on_conflict_do_nothing(index_elements=['proyecto_id', 'clave']))
    return (AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_seq')
            .populate_existing().with_for_update().one())


def siguiente(pid, year):
    minimo, _ = limites(pid, year)
    cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_seq').first()
    return max(minimo, _entero(cfg.valor if cfg else None, 30))


def reservar(pid, prefijo, fecha, sugerido=''):
    """El bloqueo dura hasta el commit de la fila; nunca confirma por separado."""
    cfg = bloquear_config(pid)
    minimo, orden = limites(pid, fecha.year)
    cfg_orden = AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_order').first()
    if cfg_orden is None:
        cfg_orden = AppConfig(proyecto_id=pid, clave='cotizacion_next_order', valor=str(orden))
        db.session.add(cfg_orden)
    orden = max(orden, _entero(cfg_orden.valor, 1))
    numero = max(minimo, _entero(cfg.valor, 30))
    match = NUMERO.fullmatch(str(sugerido or '').strip())
    # Una sugerencia vieja o con sufijo nunca hace retroceder el consecutivo.
    if match and '.' not in str(sugerido) and int(match[1]) == fecha.year:
        numero = max(numero, int(match[2]))
    if numero > 9999999:
        raise ValueError('Se agotó el rango del correlativo de cotizaciones.')
    cfg.valor = str(numero + 1)
    cfg_orden.valor = str(orden + 1)
    key = f'{prefijo}-{fecha.year}-{fecha.month:02d}-{numero:06d}'
    return key, str(orden)
