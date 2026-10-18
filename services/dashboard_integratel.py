"""Indicadores de Integratel calculados por creación del WO (criterio operativo)."""
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

# Patrones compilados una sola vez: `re.sub`/`re.match` con patrón str los
# recompilan (con búsqueda en la caché interna) en cada llamada. En un bucle de
# decenas de miles de filas esa sobrecarga se vuelve significativa.
_PATRON_NO_ALNUM = re.compile(r'[^a-z0-9]')
_PATRON_FECHA = re.compile(r'^(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})', re.ASCII)
_PATRON_TIPO_WO = re.compile(r'^(PLM|PM|CM)(?:\b|[-_0-9])')


@lru_cache(maxsize=8192)
def _normalizar_texto(texto):
    """Normalización memoizada: los nombres de campo se repiten en cada fila."""
    return _PATRON_NO_ALNUM.sub('', unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower())


def normalizar(value):
    value = value or ''
    if not isinstance(value, str):
        value = str(value)
    return _normalizar_texto(value)


def fecha(value):
    text = str(value or '').strip()
    match = _PATRON_FECHA.match(text)
    if not match:
        return None
    trozo = match[1]
    # Se arma la fecha directamente (strptime cuesta ~30 µs por fila), con el
    # mismo orden de formatos de antes: AAAA-MM-DD y luego DD/MM/AAAA o DD-MM-AAAA.
    if len(trozo) == 10 and trozo[4] == '-':
        anio, mes, dia = trozo[0:4], trozo[5:7], trozo[8:10]
    else:
        partes = trozo.split('/')
        if len(partes) != 3:
            partes = trozo.split('-')
        if len(partes) != 3 or len(partes[2]) != 4:
            return None
        dia, mes, anio = partes
    try:
        return date(int(anio), int(mes), int(dia))
    except ValueError:
        return None


def _claves(*nombres):
    """Normaliza los nombres de campo de una búsqueda una sola vez."""
    return tuple(normalizar(n) for n in nombres)


# Claves ya normalizadas: `valor(...)` se ejecuta decenas de miles de veces por
# render, así que normalizar sus literales en cada llamada era trabajo repetido.
_K_FASE = _claves('OPERATE PHASE', 'OPHERATE PHASE')
_K_CREACION = _claves('Fecha de creación (WO Creation date)', 'FECHA DE CREACION',
                      'FECHA CREACION', 'WO CREATION DATE', 'CREATION TIME', 'CREATE TIME')
_K_WO = _claves('NÚMERO DE WO', 'NUMERO WO', 'WO NUMBER', '_key')
_K_TIPO_WO = _claves('TIPO WO')
_K_DEPARTAMENTO = _claves('DEPARTAMENTO')
_K_SITE = _claves('NOMBRE DE SITE', 'NOMBRE SITE', 'SITE NAME', 'SITE')
_K_TAREA = _claves('Tipo tarea', 'TIPO DE TAREA', 'TIPO TAREA')
_K_PERSONAL = _claves('Nombre de personal FLM asignado', 'PERSONAL FLM ASIGNADO',
                      'FLM ASIGNADO', 'TECNICO ASIGNADO')
_K_PRIORIDAD = _claves('Prioridad del Site', 'PRIORIDAD SITE')
_K_FAULT = _claves('Fault Level', 'NIVEL DE FALLA')


def indicadores(rows, hoy=None):
    hoy = hoy or datetime.now(ZoneInfo('America/Lima')).date()
    actual = hoy.strftime('%Y-%m')
    meses, departamentos, sites, fases = Counter(), Counter(), Counter(), Counter()
    tipos = defaultdict(Counter)
    produccion = backlog = abiertos_actual = sin_fecha = futuros = total = 0
    detalle = []
    claves_por_fila = {}
    for row in rows:
        total += 1
        fields = {}
        # Las filas de un WO comparten las mismas claves: cada nombre de campo se
        # normaliza una sola vez por juego de claves (antes: en cada fila).
        firma = tuple(row)
        pares = claves_por_fila.get(firma)
        if pares is None:
            pares = [(normalizar(k), k) for k in row]
            claves_por_fila[firma] = pares
        for normalized, key in pares:
            value = row[key]
            if normalized not in fields or fields[normalized] in (None, ''):
                fields[normalized] = value
        def valor(*keys):
            for k in keys:
                actual = fields.get(k)
                if actual not in (None, ''):
                    return actual
            return ''
        phase = str(valor(*_K_FASE)).strip().lower()
        creation = fecha(valor(*_K_CREACION))
        month = creation.strftime('%Y-%m') if creation else None
        wo = str(valor(*_K_WO)).strip()
        match = _PATRON_TIPO_WO.match(str(valor(*_K_TIPO_WO) or wo).upper())
        tipo = match.group(1) if match else 'Otros'
        dept = str(valor(*_K_DEPARTAMENTO)).strip() or 'Sin departamento'
        site = str(valor(*_K_SITE)).strip() or 'Sin site'
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
        detalle.append({'wo':wo,'tipo':tipo,'mes':month or '',
                        'fecha':creation.isoformat() if creation else '',
                        'tarea':str(valor(*_K_TAREA)).strip() or 'Sin tipo de tarea',
                        'personal':str(valor(*_K_PERSONAL)).strip() or 'Sin personal asignado',
                        'prioridad':str(valor(*_K_PRIORIDAD)).strip() or 'Sin prioridad',
                        'fault':str(valor(*_K_FAULT)).strip() or 'Sin Fault Level',
                        'departamento':dept,'site':site,'fase':phase or 'Sin fase','grupo':grupo})
    return {'mes_actual':actual,'total':total,'produccion':produccion,'backlog':backlog,'en_atencion':abiertos_actual,
            'sin_fecha':sin_fecha,'futuros':futuros,'meses':dict(sorted(meses.items())),
            'departamentos':departamentos.most_common(),'sites':sites.most_common(),
            'tipos':{k:dict(v) for k,v in tipos.items()},'fases':fases.most_common(),'detalle':detalle}
