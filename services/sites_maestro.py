"""Nombres de sites del maestro SITE: fuente única del autocompletado.

El módulo SITE guarda el nombre de cada sitio en la columna ``Nombre``. Antes
cada endpoint tenía su propia lista de claves aceptadas y el autocompletado
genérico devolvía siempre una lista vacía. Aquí se resuelve en un solo lugar,
sin consultar otros módulos (decisión de negocio: solo el maestro SITE).
"""
import json

from db import db
from models import NucleusData, Proyecto

# Claves (=columnas) que pueden contener el nombre del site, en orden de
# preferencia. Se comparan sin distinguir mayúsculas ni acentos por la vía de
# `str.upper()`; "NOMBRE" es la columna real del maestro.
CLAVES_NOMBRE = ('NOMBRE', 'NOMBRE SITE', 'NOMBRE DE SITE', 'NOMBRE DEL SITE',
                 'SITE', 'SITE NAME')


def _clave_nombre(datos):
    """Primera clave de CLAVES_NOMBRE presente en la fila, o None."""
    por_clave = {}
    for clave in datos:
        por_clave.setdefault(str(clave or '').strip().upper(), clave)
    for clave in CLAVES_NOMBRE:
        encontrada = por_clave.get(clave)
        if encontrada is not None:
            return encontrada
    return None


def nombres_maestro():
    """Nombres distintos registrados en el maestro SITE, ordenados.

    Solo se lee ``data_json`` (sin materializar entidades ORM) y por lotes: el
    maestro tiene miles de filas y esta lista se pide al abrir los formularios.
    """
    ids = [p.id for p in Proyecto.query.filter_by(nombre='SITE').all()]
    if not ids:
        return []
    nombres = set()
    # Las filas de un mismo maestro comparten las mismas claves: el campo de
    # nombre se resuelve una sola vez por juego de claves.
    columna_por_firma = {}
    pendiente = object()
    filas = (db.session.query(NucleusData.data_json)
             .filter(NucleusData.proyecto_id.in_(ids))
             .yield_per(500))
    for (data_json,) in filas:
        try:
            datos = json.loads(data_json or '{}')
        except (ValueError, TypeError):
            continue
        if not isinstance(datos, dict):
            continue
        firma = tuple(datos)
        clave = columna_por_firma.get(firma, pendiente)
        if clave is pendiente:
            clave = _clave_nombre(datos)
            columna_por_firma[firma] = clave
        if clave is not None:
            valor = str(datos.get(clave) or '').strip()
            if valor:
                nombres.add(valor)
    return sorted(nombres)
