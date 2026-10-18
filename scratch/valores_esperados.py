# -*- coding: utf-8 -*-
"""Valores reales de las funciones puras: base para la tabla de casos de la
estrategia de testing. No modifica nada; solo observa y reporta."""
import sys

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
sys.stdout.reconfigure(encoding='utf-8')

from decimal import Decimal  # noqa: E402
from services.normalizacion import normalizar, primer_texto  # noqa: E402
from blueprints.refacturable import _monto, _importe  # noqa: E402
from config import _normalizar_db_url  # noqa: E402
from services.dashboard_integratel import fecha  # noqa: E402

print('== normalizar ==')
for caso in ['Ñandú', 'WO-123 / A', 'ABC_1', '١٢٣', '  x  ', None, 123, '', 'ÁÉÍÓÚ']:
    print('  %-14s -> %r' % (ascii(caso), normalizar(caso)))

print('== primer_texto ==')
print('  (None,"","  x  ") ->', ascii(primer_texto(None, '', '  x  ')))
print('  (0, 5)           ->', ascii(primer_texto(0, 5)))

print('== _monto ==')
for caso in ['S/ 1,234.56', '1.234,56', '1,5', 'abc', 'NaN', 'Infinity',
             'S/', 'PEN', '999999999999', '1000000000000', '1e5', '-5,00', None, '']:
    print('  %-16s -> %r' % (ascii(caso), _monto(caso)))

print('== _importe ==')
print('  None ->', ascii(_importe(None)), '| 1.5 ->', ascii(_importe(Decimal('1.5'))))

print('== _normalizar_db_url ==')
for url in [None, 'sqlite:///x.db', 'postgres://u:p@h/db',
            'postgresql://h/db?channel_binding=require',
            'postgresql://h/db?channel_binding=require&sslmode=require',
            'postgresql://h/db?sslmode=require&channel_binding=require']:
    print('  %-50s -> %r' % (ascii(url), _normalizar_db_url(url)))

print('== fecha (dashboard) ==')
for caso in ['2026-08-14 12:46:17', '14/08/2026', '2/1/2026 8:5', '2026-08-14',
             '', None, 'no-es-fecha', '14-08-2026', '2026/08/14']:
    try:
        salida = repr(fecha(caso))
    except Exception as error:  # noqa: BLE001
        salida = 'ERROR %s' % type(error).__name__
    print('  %-22s -> %s' % (ascii(caso), salida))
