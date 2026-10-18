# -*- coding: utf-8 -*-
"""Presupuesto de consultas por endpoint (regresión de los N+1).

Capa 2 de la estrategia (docs/estrategia_testing.md §4.7). En producción la
base es Postgres remoto: cada consulta es una ida y vuelta por red, así que el
número de SQL pesa más que los milisegundos locales.

Los topes son holgados a propósito: atrapan una regresión grave (por ejemplo el
N+1 de `/api/rendicion/validadores`, que hacía 94 consultas) sin volverse
frágiles ante un cambio pequeño y legítimo.
"""
import pytest
from sqlalchemy import event

from db import db
from models import Proyecto

# ruta -> (consultas medidas, tope permitido)
PRESUPUESTO = {
    '/': (9, 20),
    '/analytics': (3, 10),
    '/api/sites': (2, 8),
    '/api/sites/nombres': (6, 12),
    '/api/catalogos/autocompletar': (2, 8),
    '/api/rendicion/validadores': (6, 12),
}


@pytest.fixture()
def contador_sql(app):
    """Cuenta las consultas SQL que se ejecutan mientras dura la prueba."""
    with app.app_context():
        contador = {'n': 0}

        def _escucha(*_args, **_kwargs):
            contador['n'] += 1

        event.listen(db.engine, 'before_cursor_execute', _escucha)
        yield contador
        event.remove(db.engine, 'before_cursor_execute', _escucha)


def test_presupuesto_de_consultas_por_endpoint(app, auth_client, contador_sql):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
    auth_client.get('/switch_project/%s' % pid)

    excesos = []
    for ruta, (_, tope) in PRESUPUESTO.items():
        auth_client.get(ruta)            # calentamiento (cachés por petición)
        contador_sql['n'] = 0
        respuesta = auth_client.get(ruta)
        assert respuesta.status_code < 500, (ruta, respuesta.status_code)
        if contador_sql['n'] > tope:
            excesos.append((ruta, contador_sql['n'], tope))

    assert not excesos, 'endpoints por encima del presupuesto (ruta, sql, tope): %s' % excesos
