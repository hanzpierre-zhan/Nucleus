# -*- coding: utf-8 -*-
"""Unitarios de `config._normalizar_db_url` (resolución de la cadena de conexión).

Capa 1 de la estrategia (`docs/estrategia_testing.md` §3.5). Es la función que
decide la conexión a la base: un fallo aquí impide arrancar.
"""
import pytest

from config import _normalizar_db_url


@pytest.mark.parametrize('url, esperado', [
    # normal
    (None, None),
    ('', ''),
    ('sqlite:///x.db', 'sqlite:///x.db'),
    ('postgres://u:p@h/db', 'postgresql+psycopg2://u:p@h/db?sslmode=require'),
    ('postgresql://h/db', 'postgresql+psycopg2://h/db?sslmode=require'),
    # ya trae sslmode: no se duplica
    ('postgresql://h/db?sslmode=require',
     'postgresql+psycopg2://h/db?sslmode=require'),
    # channel_binding se elimina
    ('postgresql://h/db?channel_binding=require',
     'postgresql+psycopg2://h/db?sslmode=require'),
    ('postgresql://h/db?sslmode=require&channel_binding=require',
     'postgresql+psycopg2://h/db?sslmode=require'),
])
def test_normaliza_url(url, esperado):
    assert _normalizar_db_url(url) == esperado


def test_channel_binding_antes_de_sslmode_comportamiento_actual():
    """BUG conocido (`docs/estrategia_testing.md` §3.5).

    Si `channel_binding` va ANTES de `sslmode`, al eliminarlo desaparece también
    el `?` y la cadena queda malformada (`/db&sslmode=require`). Se fija el
    comportamiento ACTUAL a propósito: corregirlo cambiaría el resultado
    observable, y aquí no se cambia nada. Si algún día se corrige, este test
    debe actualizarse de forma deliberada.
    """
    assert _normalizar_db_url(
        'postgresql://h/db?channel_binding=require&sslmode=require'
    ) == 'postgresql+psycopg2://h/db&sslmode=require'
