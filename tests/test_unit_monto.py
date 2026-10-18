# -*- coding: utf-8 -*-
"""Unitarios de `_monto` / `_importe` (`blueprints/refacturable.py`).

Capa 1 de la estrategia (`docs/estrategia_testing.md` §3.3): parsing de importes
en la liquidación. Un error aquí se traduce en un monto mal guardado.
"""
from decimal import Decimal

import pytest

from blueprints.refacturable import _importe, _monto


@pytest.mark.parametrize('entrada, esperado', [
    # normal
    ('1234.56', Decimal('1234.56')),
    ('S/ 1,234.56', Decimal('1234.56')),
    ('1.234,56', Decimal('1234.56')),      # formato europeo
    ('1,5', Decimal('1.50')),              # coma decimal + cuantización
    ('-5,00', Decimal('-5.00')),
    # límite: justo en el tope permitido
    ('999999999999', Decimal('999999999999.00')),
    # límite: notación científica aceptada (comportamiento actual)
    ('1e5', Decimal('100000.00')),
])
def test_monto_valido(entrada, esperado):
    assert _monto(entrada) == esperado


@pytest.mark.parametrize('entrada', [
    'abc',              # no numérico
    'NaN',              # no finito
    'Infinity',         # no finito
    'S/',               # solo prefijo
    'PEN',              # solo prefijo
    '',                 # vacío
    None,               # nulo
    '1000000000000',    # por encima del tope
])
def test_monto_invalido(entrada):
    assert _monto(entrada) is None


@pytest.mark.parametrize('valor, esperado', [
    (None, ''),
    (Decimal('1.5'), '1.50'),
    (Decimal('0'), '0.00'),
])
def test_importe(valor, esperado):
    assert _importe(valor) == esperado
