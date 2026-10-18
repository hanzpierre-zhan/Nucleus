# -*- coding: utf-8 -*-
"""fecha() nuevo vs la versión con strptime, sobre un corpus grande."""
import itertools
import re
import sys
from datetime import datetime

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
from services.dashboard_integratel import fecha as fecha_nueva  # noqa: E402

_PATRON_FECHA = re.compile(r'^(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})')


def fecha_vieja(value):
    text = str(value or '').strip()
    match = _PATRON_FECHA.match(text)
    if not match:
        return None
    for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(match[1], pattern).date()
        except ValueError:
            pass
    return None


corpus = []
# ISO válidos e inválidos
for a in (2024, 2026, 1999, 1234):
    for m in (1, 2, 9, 11, 12, 13, 30, 99):
        for d in (1, 5, 9, 28, 29, 30, 31, 32, 99):
            corpus.append('%04d-%02d-%02d' % (a, m, d))
corpus.append('0001-01-01')
# formato dd/mm/aaaa y dd-mm-aaaa, con 1 o 2 dígitos
for a in (2024, 2026):
    for d, m in itertools.product((1, 2, 9, 28, 29, 30, 31, 0, 32), (1, 2, 9, 12, 13, 0)):
        for sep in ('/', '-'):
            corpus.append(f'{d}{sep}{m}{sep}{a}')
            corpus.append(f'{d:02d}{sep}{m:02d}{sep}{a}')
# con hora, espacios, textos raros y separadores mezclados
for extra in (' 12:30:45', 'T08:00', 'xyz', '', ' ', 'UTC'):
    corpus += ['2026-10-17' + extra, '17/10/2026' + extra, '17-10-2026' + extra]
corpus += ['1/2-2024', '1-2/2024', '12-34-2024', '12/34/2024', '20 24-10-17',
           '2024-1-1', '2024/10/17', '17.10.2026', '', '   ', 'sin fecha', None,
           20261017, '0000-01-01', '9999-12-31', '2024-02-30', '2024-13-01', '31/02/2024']
# dígitos unicode
corpus += ['٢٠٢٤-٠١-٠٢', '١٧/١٠/٢٠٢٦']

dif = 0
for texto in corpus:
    a, b = fecha_vieja(texto), fecha_nueva(texto)
    if a != b:
        dif += 1
        if dif <= 12:
            print(f'  DIF {ascii(texto)}: vieja={a} nueva={b}')
print(f'corpus: {len(corpus)} casos, diferencias: {dif}')
print('IDÉNTICO' if dif == 0 else 'HAY DIFERENCIAS')
