"""Indicadores de Integratel calculados por creación del WO (criterio operativo)."""
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo


def normalizar(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower())


def fecha(value):
    text = str(value or '').strip()
    match = re.match(r'^(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})', text)
    if not match:
        return None
    for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(match[1], pattern).date()
        except ValueError:
            pass
    return None


def indicadores(rows, hoy=None):
    hoy = hoy or datetime.now(ZoneInfo('America/Lima')).date()
    actual = hoy.strftime('%Y-%m')
    meses, departamentos, sites, fases = Counter(), Counter(), Counter(), Counter()
    tipos = defaultdict(Counter)
    produccion = backlog = abiertos_actual = sin_fecha = futuros = total = 0
    detalle = []
    for row in rows:
        total += 1
        fields = {}
        for key, value in row.items():
            normalized = normalizar(key)
            if normalized not in fields or fields[normalized] in (None, ''):
                fields[normalized] = value
        def valor(*keys):
            return next((fields[normalizar(k)] for k in keys if fields.get(normalizar(k)) not in (None, '')), '')
        phase = str(valor('OPERATE PHASE', 'OPHERATE PHASE')).strip().lower()
        creation = fecha(valor('Fecha de creación (WO Creation date)', 'FECHA DE CREACION', 'FECHA CREACION', 'WO CREATION DATE', 'CREATION TIME', 'CREATE TIME'))
        month = creation.strftime('%Y-%m') if creation else None
        wo = str(valor('NÚMERO DE WO', 'NUMERO WO', 'WO NUMBER', '_key')).strip()
        match = re.match(r'^(PLM|PM|CM)(?:\b|[-_0-9])', str(valor('TIPO WO') or wo).upper())
        tipo = match.group(1) if match else 'Otros'
        dept = str(valor('DEPARTAMENTO')).strip() or 'Sin departamento'
        site = str(valor('NOMBRE DE SITE', 'NOMBRE SITE', 'SITE NAME', 'SITE')).strip() or 'Sin site'
        if phase == 'close':
            grupo = 'Producción'
            produccion += 1
            departamentos[dept] += 1
            sites[site] += 1
            if month: meses[month] += 1
        else:
            fases[phase or 'Sin fase'] += 1
            if month is None: grupo = 'Sin fecha'
            elif month < actual: grupo = 'Backlog'; backlog += 1
            elif month == actual: grupo = 'En atención'; abiertos_actual += 1
            else: grupo = 'Fecha futura'; futuros += 1
        if month is None: sin_fecha += 1
        tipos[grupo][tipo] += 1
        detalle.append({'wo':wo,'tipo':tipo,'mes':month or '', 'departamento':dept,'site':site,'fase':phase or 'Sin fase','grupo':grupo})
    return {'mes_actual':actual,'total':total,'produccion':produccion,'backlog':backlog,'en_atencion':abiertos_actual,
            'sin_fecha':sin_fecha,'futuros':futuros,'meses':dict(sorted(meses.items())),
            'departamentos':departamentos.most_common(),'sites':sites.most_common(),
            'tipos':{k:dict(v) for k,v in tipos.items()},'fases':fases.most_common(),'detalle':detalle}
