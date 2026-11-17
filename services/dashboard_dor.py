"""Operación diaria CM (Claro): datos por ticket para el dashboard tipo "Daily Operation Report".

El servidor solo arma una fila liviana por ticket CM; los cálculos por día (SLA, backlog,
flujo, cierre desde el despacho, eficiencia, tiempos y causa raíz) se hacen en el navegador
para que los filtros respondan al instante.
"""
import re

from services.dashboard_claro import region
from services.dashboard_integratel import instante, normalizar

_CERRADO = ('completed', 'closed', 'complete', 'close')
_CANCELADO = ('canceled', 'cancelled')

# Línea base del backlog por región (nivel aceptable de tickets abiertos al cierre del día).
LINEA_BASE = {'LIMA': 10, 'CENTRO': 24}
META_SLA = 95
META_EFICIENCIA = 2

# Familias de causa raíz (Root Cause de Claro). El orden importa: gana la primera que coincide.
FAMILIAS = (
    ('Sin causa registrada', r'^$|^DEFAULT ROOT CAUSE$'),
    ('Visita trunca', r'VISITA TRUNCA'),
    ('Falsa alarma o sin falla', r'FALSA ALARMA|ALARMA CLAREADA|NO REFLEJA ALARMA|PRUEBAS'),
    ('Baterías y autonomía', r'BATERIA|AUTONOMIA'),
    ('Corte de energía comercial', r'CORTE MAYOR|CORTE ENERGIA|^LMT$|NODO AFECTADO'),
    ('Grupo electrógeno', r'COMBUSTIBLE|ALTERNADOR|RADIADOR|ARRANCADOR|CONTROL GE|GRUPO'),
    ('Aire acondicionado', r'EVAPORADOR|COMPRESOR|AIRE|CONDENSADORA|VENTILADOR'),
    ('Transmisión y fibra', r'^DWDM|^MW-|^DEFINITIVA|^PROVISIONAL|JUMPER|TRANSCEIVER|CONECTOR|HERMETIZADO|FIBRA|EMPALME'),
    ('Radio y equipos de red', r'^RRU$|^BBU$|CONFIGURACION|ANTENA|TARJETA'),
    ('Equipos de energía', r'BREAKER|BREACKER|RECTIFICADOR|CONDENSADOR|CONTACTOR|VOLTAJE|UNIDAD CONTROL|^AVR$|CONTROL TTA|CESE AUTOMATICO'),
    ('Terceros, seguridad e infraestructura', r'TERCEROS|PROPIETARIO|PUERTA|ROBO|VANDALISMO|SEGURIDAD'),
)
_FAMILIAS_RE = [(nombre, re.compile(patron)) for nombre, patron in FAMILIAS]


def familia(causa):
    texto = re.sub(r'\s+', ' ', normalizar_texto(causa))
    for nombre, patron in _FAMILIAS_RE:
        if patron.search(texto):
            return nombre
    return 'Otras causas'


def normalizar_texto(valor):
    import unicodedata
    texto = unicodedata.normalize('NFKD', str(valor or '')).encode('ascii', 'ignore').decode()
    return texto.strip().upper()


def ultima_importacion(proyecto_id):
    """Fecha y hora (Perú) de la última importación del proyecto: el corte de los datos.

    Se guarda en AppConfig 'ultima_importacion' en cada importación; para lo importado antes
    de este cambio se usa el último registro del historial hecho por la importación."""
    import json
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from models import AppConfig, HistorialCambios
    fecha, usuario = None, ''
    cfg = AppConfig.query.filter_by(proyecto_id=proyecto_id, clave='ultima_importacion').first()
    if cfg and cfg.valor:
        try:
            dato = json.loads(cfg.valor)
            fecha, usuario = datetime.fromisoformat(dato.get('fecha')), dato.get('usuario') or ''
        except (ValueError, TypeError):
            fecha = None
    if fecha is None:
        fecha = HistorialCambios.query.with_entities(func.max(HistorialCambios.fecha)).filter_by(proyecto_id=proyecto_id, username='IMPORT').scalar()
    if fecha is None:
        return None
    lima = fecha - timedelta(hours=5)  # se guarda en UTC
    return {'texto': lima.strftime('%d/%m/%Y %H:%M'), 'usuario': usuario}


def indicadores(registros):
    rows = []
    for raw in registros:
        d = {normalizar(k): v for k, v in raw.items()}

        def text(*claves):
            return next((str(d[normalizar(k)]).strip() for k in claves if str(d.get(normalizar(k)) or '').strip()), '')

        ticket = text('Ticket Id')
        tipo = (text('Task Type') or ticket.split('-')[0]).upper()
        if not ticket or tipo != 'CM':
            continue
        estado = text('Task Status').casefold()
        cancelado = estado in _CANCELADO
        completado = estado in _CERRADO
        despacho = instante(text('Dispatch Time'))
        sla = text('SLA Status').casefold()
        oficina = text('FM Office', 'FM  Office Site') or 'Sin oficina'
        causa = text('Root Cause')
        rows.append({
            'id': ticket, 'site': text('Site ID', 'Site Name'), 'nombre_site': text('Site Name'),
            'oficina': oficina, 'region': region(oficina), 'contrata': text('FME Contractor') or 'Sin contrata',
            'tecnico': text('Assign To FME Full Name', 'Assign To FME') or 'Sin técnico',
            'estado': estado, 'completado': completado, 'cancelado': cancelado,
            'creado': instante(text('Create Time')), 'despacho': despacho,
            'llegada': instante(text('Arrive Time')),
            'cierre': instante(text('Complete Time')) if completado else None,
            # Claro casi no trae Cancel Time: se usa la fecha del cambio de estado o, si no hay, la del despacho.
            'cancelacion': (instante(text('Cancel Time', '_fecha_cancel_reject', 'FECHA CAMBIO ESTADO')) or despacho) if cancelado else None,
            'sla': True if sla == 'normal' else False if sla in ('sla_violation', 'milestone_broken') else None,
            'sla_texto': text('SLA Status'),
            'parada': text('Suspend State').casefold() == 'suspend',
            'causa': causa or '(sin causa)', 'familia': familia(causa),
            'categoria': text('Task Category'),
        })
    fechas = [r[k][:10] for r in rows for k in ('creado', 'despacho', 'cierre') if r[k]]
    return {'rows': rows, 'total': len(rows), 'hasta': max(fechas, default=''),
            'linea_base': LINEA_BASE, 'meta_sla': META_SLA, 'meta_eficiencia': META_EFICIENCIA,
            'familias': [n for n, _ in FAMILIAS] + ['Otras causas']}
