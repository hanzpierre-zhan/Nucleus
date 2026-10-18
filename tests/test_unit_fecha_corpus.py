# -*- coding: utf-8 -*-
"""Equivalencia de `fecha()` contra su implementación legacy (strptime).

Promueve a test permanente el corpus que se usó durante la optimización
(`scratch/equiv_fecha.py`): la versión actual debe devolver exactamente lo mismo
que la original sobre casos válidos, límite e inválidos.

Capa 1 de la estrategia (`docs/estrategia_testing.md` §3.4).
"""
import itertools
import re
from datetime import datetime

from services.dashboard_integratel import fecha

# Implementación ORIGINAL, congelada aquí como referencia (no se usa en la app).
_PATRON_LEGACY = re.compile(r'^(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})')


def _fecha_legacy(value):
    text = str(value or '').strip()
    match = _PATRON_LEGACY.match(text)
    if not match:
        return None
    for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(match[1], pattern).date()
        except ValueError:
            pass
    return None


def _corpus():
    corpus = []
    # ISO (válidos e inválidos: meses/días fuera de rango)
    for anyo in (2024, 2026, 1999, 1234):
        for mes in (1, 2, 9, 11, 12, 13, 30, 99):
            for dia in (1, 5, 9, 28, 29, 30, 31, 32, 99):
                corpus.append('%04d-%02d-%02d' % (anyo, mes, dia))
    corpus.append('0001-01-01')
    # dd/mm/aaaa y dd-mm-aaaa, con 1 o 2 dígitos
    for anyo in (2024, 2026):
        for dia, mes in itertools.product((1, 2, 9, 28, 29, 30, 31, 0, 32),
                                          (1, 2, 9, 12, 13, 0)):
            for sep in ('/', '-'):
                corpus.append(f'{dia}{sep}{mes}{sep}{anyo}')
                corpus.append(f'{dia:02d}{sep}{mes:02d}{sep}{anyo}')
    # con hora, espacios, textos raros y separadores mezclados
    for extra in (' 12:30:45', 'T08:00', 'xyz', '', ' ', 'UTC'):
        corpus += ['2026-10-17' + extra, '17/10/2026' + extra, '17-10-2026' + extra]
    corpus += ['1/2-2024', '1-2/2024', '12-34-2024', '12/34/2024', '20 24-10-17',
               '2024-1-1', '2024/10/17', '17.10.2026', '', '   ', 'sin fecha', None,
               20261017, '0000-01-01', '9999-12-31', '2024-02-30', '2024-13-01', '31/02/2024']
    # dígitos unicode
    corpus += ['٢٠٢٤-٠١-٠٢', '١٧/١٠/٢٠٢٦']
    return corpus


def test_fecha_es_equivalente_al_legacy_sobre_todo_el_corpus():
    corpus = _corpus()
    assert len(corpus) > 700, 'el corpus debe seguir siendo amplio'
    diferencias = [(ascii(texto), _fecha_legacy(texto), fecha(texto))
                   for texto in corpus if _fecha_legacy(texto) != fecha(texto)]
    assert not diferencias, 'fecha() difiere del legacy en: %s' % diferencias[:5]


def test_fecha_casos_representativos():
    assert fecha('2026-08-14 12:46:17') == datetime(2026, 8, 14).date()
    assert fecha('14/08/2026') == datetime(2026, 8, 14).date()
    assert fecha('14-08-2026') == datetime(2026, 8, 14).date()
    assert fecha('2026-08-14') == datetime(2026, 8, 14).date()
    # límite: separador con barras invertido respecto al ISO no se reconoce
    assert fecha('2026/08/14') is None
    for invalido in ('no-es-fecha', '', None):
        assert fecha(invalido) is None
