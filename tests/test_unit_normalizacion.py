# -*- coding: utf-8 -*-
"""Unitarios de `services/normalizacion.py` (funciones puras: sin app ni base).

Capa 1 de la estrategia (`docs/estrategia_testing.md` §3.1-3.2). Solo observa el
comportamiento actual; no modifica nada.
"""
import pytest

from services.normalizacion import normalizar, primer_texto


@pytest.mark.parametrize('entrada, esperado', [
    # normal
    ('WO-123 / A', 'wo123a'),
    ('Ñandú', 'nandu'),
    ('ÁÉÍÓÚ', 'aeiou'),
    ('Site Name', 'sitename'),
    # límite
    ('  x  ', 'x'),
    ('', ''),
    (None, ''),
    (123, '123'),
    # inválido (símbolos fuera del alfabeto permitido)
    ('ABC_1', 'abc1'),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_normalizar_descarta_digitos_no_ascii():
    """NFKD no convierte dígitos árabes a ASCII, así que quedan fuera.

    Comportamiento actual y documentado (§3.1): no se cambia aquí.
    """
    assert normalizar('١٢٣') == ''


def test_normalizar_es_case_insensitive_e_idempotente():
    assert normalizar('Site Name') == normalizar('site name')
    assert normalizar(normalizar('Ñandú')) == 'nandu'


@pytest.mark.parametrize('valores, esperado', [
    ((None, '', '  x  '), 'x'),
    (('  a  ', 'b'), 'a'),
    ((None, None), ''),
    (('', None), ''),
])
def test_primer_texto(valores, esperado):
    assert primer_texto(*valores) == esperado


def test_primer_texto_trata_cero_como_vacio():
    """Un `0` numérico se considera vacío (comportamiento actual, §3.2)."""
    assert primer_texto(0, 5) == '5'
