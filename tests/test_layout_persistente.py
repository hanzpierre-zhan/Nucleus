# -*- coding: utf-8 -*-
"""Regresión: ningún arranque ni carga debe pisar el layout de columnas.

Pedido del usuario: al publicar un commit las columnas cambiaban de posición o
de visibilidad en todos los proyectos. Estas pruebas fijan que la configuración
que el admin guarda (manual_columns y column_layout) sobrevive a los arranques
y a las cargas de la página, y que la fusión nunca borra columnas propias.
"""
import json
import os

import pytest

from db import db
from models import AppConfig, NucleusData, Proyecto, TablaMaestra
from migrations import _configurar_proyectos_apoyo, _fusionar_columnas
from services import columnas_fuente

CLAVES_LAYOUT = ('app_schema', 'column_layout', 'manual_columns')


def _cfg(pid, clave):
    return AppConfig.query.filter_by(proyecto_id=pid, clave=clave).first()


def _guardar(pid, clave, valor):
    cfg = _cfg(pid, clave)
    if cfg:
        cfg.valor = json.dumps(valor, ensure_ascii=False)
    else:
        db.session.add(AppConfig(proyecto_id=pid, clave=clave,
                                 valor=json.dumps(valor, ensure_ascii=False)))
    db.session.commit()


def _nombres(pid, clave='manual_columns'):
    return [c.get('nombre') for c in json.loads(_cfg(pid, clave).valor)]


def _restaurar(pid, clave, valor_crudo):
    """Devuelve la clave a su valor crudo original (o la borra si no existía)."""
    cfg = _cfg(pid, clave)
    if valor_crudo is None:
        if cfg:
            db.session.delete(cfg)
            db.session.commit()
        return
    if cfg:
        cfg.valor = valor_crudo
    else:
        db.session.add(AppConfig(proyecto_id=pid, clave=clave, valor=valor_crudo))
    db.session.commit()


# ── Unidad: fusión de columnas ──────────────────────────────────────────────
def test_fusion_preserva_orden_opciones_y_columnas_propias():
    por_defecto = [
        {'nombre': 'N° ORDEN', 'tipo': 'texto', 'opciones': []},
        {'nombre': 'FECHA', 'tipo': 'fecha', 'opciones': []},
        {'nombre': 'GESTOR', 'tipo': 'texto', 'opciones': []},
    ]
    actual = [
        {'nombre': 'MI COLUMNA', 'tipo': 'texto', 'opciones': []},
        {'nombre': 'GESTOR', 'tipo': 'lista', 'opciones': ['Ana', 'Luis']},
    ]
    fusion = _fusionar_columnas(json.dumps(actual, ensure_ascii=False), por_defecto)
    nombres = [c['nombre'] for c in fusion]
    assert nombres[0] == 'N° ORDEN'                      # siempre primero
    assert nombres.index('MI COLUMNA') < nombres.index('GESTOR')  # orden propio
    gestor = next(c for c in fusion if c['nombre'] == 'GESTOR')
    assert gestor['opciones'] == ['Ana', 'Luis']         # opciones propias intactas
    assert set(nombres) == {'N° ORDEN', 'MI COLUMNA', 'GESTOR', 'FECHA'}


def test_fusion_solo_agrega_las_que_faltan_y_es_estable():
    por_defecto = [{'nombre': 'A', 'tipo': 'texto', 'opciones': []},
                   {'nombre': 'B', 'tipo': 'texto', 'opciones': []}]
    actual = [{'nombre': 'B', 'tipo': 'texto', 'opciones': []}]
    primera = _fusionar_columnas(json.dumps(actual), por_defecto)
    segunda = _fusionar_columnas(json.dumps(primera), por_defecto)
    assert [c['nombre'] for c in primera] == ['B', 'A']
    assert primera == segunda                            # idempotente


def test_fusion_valor_ilegible_devuelve_por_defecto():
    por_defecto = [{'nombre': 'N° ORDEN', 'tipo': 'texto', 'opciones': []}]
    assert _fusionar_columnas('no es json', por_defecto) == por_defecto


# ── Arranque: manual_columns de los proyectos de apoyo ──────────────────────
@pytest.mark.parametrize('proyecto', ['Dataper', 'Material', 'SITE',
                                      'Generadores', 'Combustible'])
def test_arranque_no_pisa_manual_columns(app, proyecto):
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre=proyecto).one()
        original = _cfg(proy.id, 'manual_columns').valor
        propia = 'COLUMNA PROPIA ' + proyecto.upper()
        try:
            columnas = json.loads(original)
            columnas.insert(0, {'nombre': propia, 'tipo': 'texto', 'opciones': []})
            _guardar(proy.id, 'manual_columns', columnas)
            # Otro arranque, como el que corre en cada deploy.
            _configurar_proyectos_apoyo(db, app, Proyecto, AppConfig, NucleusData, TablaMaestra)
            despues = _nombres(proy.id)
            assert propia in despues
            assert {c.get('nombre') for c in columnas}.issubset(set(despues))
        finally:
            _guardar(proy.id, 'manual_columns', json.loads(original))


def test_segundo_arranque_no_cambia_ninguna_config_de_columnas(app):
    """Correr las migraciones dos veces (deploy) no altera lo guardado."""
    from migrations import run_migrations
    with app.app_context():
        # Primer arranque: normaliza una vez (p. ej. ordena app_schema).
        run_migrations(app, os.environ.get('DATABASE_URL', ''))
        snapshot = {}
        for p in Proyecto.query.all():
            snapshot[p.id] = {
                c.clave: c.valor
                for c in AppConfig.query.filter_by(proyecto_id=p.id)
                if c.clave in CLAVES_LAYOUT or (c.clave or '').startswith('column_layout__')
            }
        # Segundo arranque: ya no debe cambiar absolutamente nada.
        run_migrations(app, os.environ.get('DATABASE_URL', ''))
        for p in Proyecto.query.all():
            for clave, valor in snapshot[p.id].items():
                actual = _cfg(p.id, clave)
                assert (actual.valor if actual else None) == valor, \
                    'Cambió %s/%s en el segundo arranque' % (p.nombre, clave)


# ── columnas_fuente: instalado una vez, no vuelve a tocar nada ─────────────
def test_columnas_fuente_instalado_no_pisa_config(app):
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one()
        assert _cfg(proy.id, columnas_fuente.VERSION) is not None
        original_layout = _cfg(proy.id, 'column_layout').valor
        original_manual = _cfg(proy.id, 'manual_columns').valor
        original_schema = _cfg(proy.id, 'app_schema').valor
        try:
            layout_propio = [{'field': 'MI COLUMNA', 'visible': True}]
            _guardar(proy.id, 'column_layout', layout_propio)
            columnas_fuente.instalar()
            assert json.loads(_cfg(proy.id, 'column_layout').valor) == layout_propio
            assert _cfg(proy.id, 'manual_columns').valor == original_manual
            assert _cfg(proy.id, 'app_schema').valor == original_schema
        finally:
            _restaurar(proy.id, 'column_layout', original_layout)


def test_columnas_fuente_reinstalar_no_duplica_respaldo(app):
    """Si el marcador falta, reinstalar no debe romper por respaldo duplicado."""
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre='FLM - PEXT').one()
        original_layout = _cfg(proy.id, 'column_layout').valor
        original_manual = _cfg(proy.id, 'manual_columns').valor
        original_schema = _cfg(proy.id, 'app_schema').valor
        marca = _cfg(proy.id, columnas_fuente.VERSION)
        if marca:
            db.session.delete(marca)
            db.session.commit()
        try:
            columnas_fuente.instalar()   # antes lanzaba IntegrityError
        finally:
            _restaurar(proy.id, 'column_layout', original_layout)
            _restaurar(proy.id, 'manual_columns', original_manual)
            _restaurar(proy.id, 'app_schema', original_schema)


# ── Carga de página: no reordenar el layout de Cotizaciones ────────────────
def test_carga_pagina_no_reordena_layout_cotizaciones(app, auth_client):
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        pid = proy.id
        cfg_original = _cfg(pid, 'column_layout')
        original = cfg_original.valor if cfg_original else None
        try:
            layout_propio = [{'field': 'GESTOR', 'visible': True},
                             {'field': 'N° ORDEN', 'visible': False}]
            _guardar(pid, 'column_layout', layout_propio)
            with auth_client.session_transaction() as ses:
                ses['current_proyecto_id'] = pid
                ses['current_proyecto_nombre'] = 'Cotizaciones'
            respuesta = auth_client.get('/')
            assert respuesta.status_code == 200
            assert json.loads(_cfg(pid, 'column_layout').valor) == layout_propio
        finally:
            _restaurar(pid, 'column_layout', original)
