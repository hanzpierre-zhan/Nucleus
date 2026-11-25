"""Homologación interna de ítems para el análisis comercial de Cotizaciones."""
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


POR_HUELLA = {
    huella: concepto
    for concepto, huellas in json.loads(
        Path(__file__).with_name('dashboard_conceptos_catalogo.json').read_text(encoding='utf-8')
    ).items()
    for huella in huellas
}

# Primero las combinaciones más específicas, para distinguir el equipo de su traslado o combustible.
REGLAS = tuple((re.compile(patron), concepto) for patron, concepto in (
    (r'alquil\w*.{0,65}(?:grupo electrogeno|generador|\bgeps?\b)', 'Alquiler de grupo electrógeno'),
    (r'alquil\w*.{0,45}(?:camioneta|movilidad|vehiculo|\bcamion\b)', 'Alquiler de vehículo'),
    (r'(?:acarreo|acareo).{0,55}(?:grupo electrogeno|generador|\bgeps?\b)', 'Acarreo de grupo electrógeno'),
    (r'(?:acarreo|acareo).{0,45}(?:combustible|gasolina|diesel|petroleo)', 'Acarreo de combustible'),
    (r'(?:transporte|traslado|envio).{0,55}(?:grupo electrogeno|generador|\bgeps?\b)', 'Transporte de grupo electrógeno'),
    (r'\b(?:custodio|custodia)\b', 'Custodia de sitio o equipo'),
    (r'\bresguardo policial\b', 'Resguardo policial'),
    (r'^(?:pago (?:de )?)?peajes?\b', 'Peajes'),
    (r'^(?:pago (?:de )?)?viaticos?\b', 'Viáticos y alimentación'),
    (r'^(?:pago (?:de )?)?hospedaje\b', 'Hospedaje'),
    (r'^(?:pago (?:de )?|compra (?:de )?)?combustible\b', 'Combustible'),
    (r'\bfiltro de aceite\b', 'Filtro de aceite'),
    (r'\bfiltro de aire\b', 'Filtro de aire'),
    (r'\bfiltro de combustible\b', 'Filtro de combustible'),
    (r'\bgrasa conductiva\b', 'Grasa conductiva'),
    (r'\bcintillos?\b', 'Cintillos de amarre'),
    (r'\bpatch.?cord\b', 'Patch cord de fibra óptica'),
))


def concepto_item(texto):
    base = ' '.join(str(texto or '').casefold().split())
    huella = hashlib.sha256(base.encode()).hexdigest()[:20]
    if huella in POR_HUELLA:
        return POR_HUELLA[huella]
    normal = ''.join(c for c in unicodedata.normalize('NFD', base) if not unicodedata.combining(c))
    return next((concepto for patron, concepto in REGLAS if patron.search(normal)), 'Por revisar')


def contar_conceptos(datos):
    items = datos.get('ITEMS_JSON') or []
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            return {}
    if not isinstance(items, list):
        return {}
    return dict(Counter(concepto_item(item.get('texto')) for item in items if isinstance(item, dict)))
