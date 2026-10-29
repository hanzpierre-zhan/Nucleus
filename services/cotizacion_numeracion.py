"""Reserva transaccional de la secuencia compartida de Cotizaciones."""
import json
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db import db
from models import AppConfig, NucleusData

NUMERO = re.compile(r'^(?:HW|EN|CL|IN|PX)-(\d{4})-(?:(?:0[1-9]|1[0-2])-)?(\d{6,7})(?:\.\d+)?$')


class NumeroNoDisponible(ValueError):
    def __init__(self, sugerido):
        self.sugerido = sugerido
        super().__init__('El número manual no está disponible. Puedes guardar con el siguiente automático.')


class NumeracionOcupada(RuntimeError):
    pass


def conflicto_numeracion(error):
    """No confundir una FK, otra clave o un ID interno con una reserva concurrente."""
    nombre = getattr(getattr(error.orig, 'diag', None), 'constraint_name', None)
    return nombre in {'uq_cotizacion_serie_mensual', 'uq_cotizacion_orden', '_proj_key_uc'}


def _entero(valor, defecto=0):
    return int(valor) if str(valor or '').isdigit() else defecto


def limites(pid, year):
    """Incluye claves históricas y excepciones recuperadas, de todos los clientes."""
    max_numero, max_orden = 29, 0
    # Lectura interna Core: el contador abarca todo el módulo, aunque el ORM
    # filtre al usuario por cliente. Solo se devuelven contadores, nunca filas.
    tabla = NucleusData.__table__
    consulta = select(tabla.c.key_value, tabla.c.data_json).where(tabla.c.proyecto_id == pid)
    for key, raw in db.session.execute(consulta):
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


def reservar(pid, prefijo, fecha, sugerido='', *, manual=False):
    """El bloqueo dura hasta el commit de la fila; nunca confirma por separado."""
    cfg = bloquear_config(pid)
    minimo, orden = limites(pid, fecha.year)
    cfg_orden = AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_order').first()
    if cfg_orden is None:
        cfg_orden = AppConfig(proyecto_id=pid, clave='cotizacion_next_order', valor=str(orden))
        db.session.add(cfg_orden)
    orden = max(orden, _entero(cfg_orden.valor, 1))
    numero = max(minimo, _entero(cfg.valor, 30))
    texto = str(sugerido or '').strip()
    if manual and re.fullmatch(r'\d{1,7}', texto):
        texto = f'{prefijo}-{fecha.year}-{fecha.month:02d}-{int(texto):06d}'
    match = NUMERO.fullmatch(texto)
    # En automático, toda sugerencia del navegador es solo provisional.
    if manual:
        if not match or '.' in texto or int(match[1]) != fecha.year:
            raise ValueError('El número manual debe tener el formato de cotización del año actual, sin sufijos.')
        if int(match[2]) < numero:
            raise NumeroNoDisponible(f'{prefijo}-{fecha.year}-{fecha.month:02d}-{numero:06d}')
        numero = int(match[2])
    if numero > 9999999:
        raise ValueError('Se agotó el rango del correlativo de cotizaciones.')
    cfg.valor = str(numero + 1)
    cfg_orden.valor = str(orden + 1)
    key = f'{prefijo}-{fecha.year}-{fecha.month:02d}-{numero:06d}'
    return key, str(orden)


def crear(pid, prefijo, fecha, datos, *, manual=False):
    """Solo reintenta colisiones conocidas y después de revertir toda el alta."""
    for intento in range(3):
        try:
            key, orden = reservar(pid, prefijo, fecha, datos.get('N° COTIZACION', ''), manual=manual)
            guardados = {**datos, 'N° COTIZACION': key, 'N° ORDEN': orden}
            fila = NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps(guardados, ensure_ascii=False))
            db.session.add(fila)
            db.session.commit()
            return {'success': True, 'key': key, 'numero': key, 'orden': orden}
        except IntegrityError as error:
            db.session.rollback()
            if not conflicto_numeracion(error):
                raise
            if manual:
                proximo = siguiente(pid, fecha.year)
                raise NumeroNoDisponible(f'{prefijo}-{fecha.year}-{fecha.month:02d}-{proximo:06d}') from error
            if intento == 2:
                raise NumeracionOcupada('No se pudo confirmar un número disponible. No se guardó la solicitud; tus datos siguen en el formulario.') from error
