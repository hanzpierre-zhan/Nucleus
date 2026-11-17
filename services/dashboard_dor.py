"""Operación diaria CM (Claro, Integratel, Entel y PEXT): datos por ticket para el dashboard tipo "Daily Operation Report".

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


# Columnas de cada proyecto (se toma la primera que tenga dato). El técnico es siempre el NOMBRE completo.
CAMPOS = {
    'CLARO': {
        'titulo': 'FLM - Claro', 'id': ('Ticket Id',), 'tipo': ('Task Type',), 'estado': ('Task Status',),
        'creado': ('Create Time',), 'despacho': ('Dispatch Time',), 'llegada': ('Arrive Time',), 'cierre': ('Complete Time',),
        'cancelacion': ('Cancel Time', '_fecha_cancel_reject', 'FECHA CAMBIO ESTADO'),
        'sla': ('SLA Status',), 'oficina': ('FM Office', 'FM  Office Site'), 'contrata': ('FME Contractor',),
        'tecnico': ('Assign To FME Full Name',), 'rm': (), 'site': ('Site ID', 'Site Name'),
        'causa': ('Root Cause',), 'familia': None, 'parada': ('Suspend State', 'suspend'),
        'etiquetas': {'oficina': 'FM Office', 'rm': '', 'causa': 'Root Cause', 'familia': 'familias de causa (agrupadas desde Root Cause)'},
    },
    'INTEGRATEL': {
        'titulo': 'FLM - Integratel', 'id': ('Task Id',), 'tipo': ('Task Type',), 'estado': ('Task Status',),
        'creado': ('Createtime', 'Create Time'), 'despacho': ('Dispatch Time',), 'llegada': ('Arrive Time',),
        # El SLA termina en el primer cierre (si lo reabren no cuenta).
        'cierre': ('First Complete Time', 'Complete Time'), 'cancelacion': ('Cancel Time', 'FECHA CAMBIO ESTADO'),
        'sla': ('Sla Status', 'SLA Status'), 'oficina': ('Fm Office',), 'contrata': ('FME contrator', 'Company Supply'),
        'tecnico': ('Assign To Fme Full Name',), 'rm': (), 'site': ('Site Id', 'Site Id Name'),
        'causa': ('Com Fault Cause',), 'familia': ('Com Fault Speciality',), 'parada': ('Suspend State', 'suspend'),
        'etiquetas': {'oficina': 'Fm Office', 'rm': '', 'causa': 'Com Fault Cause', 'familia': 'especialidad de la falla (Com Fault Speciality)'},
    },
    'ENTEL': {
        'titulo': 'FLM - Entel', 'id': ('Task ID(create)', 'id', 'Ticket ID'), 'tipo': (), 'estado': ('Ticket Status', 'Estado de la tarea (WO State)'),
        'creado': ('CreateTime(create)',), 'despacho': ('dispatch_time',), 'llegada': ('arrive_time',), 'cierre': ('SubmitTime(complete)', 'complete_time'),
        'cancelacion': ('Cancel Time',), 'sla': ('SLA Status',), 'oficina': ('fm_office',), 'contrata': ('Contractor',),
        'tecnico': ('assign_to_fme',), 'rm': ('Region Manager(create)',), 'site': ('Site ID(create)',),
        'causa': ('Task Subcategory(create)',), 'familia': ('Task Category(create)',), 'parada': ('SLA Paused', 'yes'),
        'etiquetas': {'oficina': 'FM Office', 'rm': 'Regional Manager', 'causa': 'Task Subcategory', 'familia': 'categoría de la tarea (Task Category)'},
    },
    'PEXT': {
        'titulo': 'FLM - PEXT', 'id': ('Número de WO', 'Numero de WO'), 'tipo': (), 'estado': ('Estado de la tarea (WO State)', 'Estado de la tarea'),
        'creado': ('Fecha de creación (WO Creation date)', 'Fecha de creacion'), 'despacho': ('Fecha de creación (WO Creation date)', 'Fecha de creacion'),
        'llegada': (), 'cierre': ('Fecha y hora de WO a estado complete', 'Fecha y hora de WO a estado close'),
        'cancelacion': ('Fecha y hora de cancelación de WO', 'FECHA CAMBIO ESTADO'), 'sla': (), 'oficina': ('Departamento',),
        'contrata': ('CONTRATA',), 'tecnico': ('Nombre de personal FLM asignado', 'TECNICO ASIGNADO'), 'rm': ('O&M asignado',),
        'site': ('Código Site', 'Nombre de Site'), 'causa': ('Causa raíz', 'Causa raiz'), 'familia': ('Tipo tarea',),
        'parada': ('Estado suspendido', 'yes'), 'objetivo_horas': ('Hrs Respuesta',),
        'etiquetas': {'oficina': 'Departamento', 'rm': 'O&M asignado', 'causa': 'Causa raíz', 'familia': 'tipo de tarea'},
    },
}


def _region(operador, oficina):
    texto = normalizar_texto(oficina)
    if operador == 'PEXT':  # por departamento: Lima/Callao y el resto
        return 'LIMA' if texto in ('LIMA', 'CALLAO') else 'PROVINCIAS' if texto else 'Sin región'
    return region(oficina)


def _horas(texto):
    m = re.search(r'(\d+(?:[.,]\d+)?)', str(texto or ''))
    return float(m[1].replace(',', '.')) if m else None


def indicadores(registros, operador='CLARO'):
    cfg = CAMPOS[operador]
    rows = []
    for raw in registros:
        d = {normalizar(k): v for k, v in raw.items()}

        def text(clave):
            return next((str(d[normalizar(k)]).strip() for k in cfg.get(clave) or () if str(d.get(normalizar(k)) or '').strip()), '')

        ticket = text('id')
        tipo = (text('tipo') or ticket.split('-')[0]).upper()
        if not ticket or tipo != 'CM':
            continue
        estado = text('estado').casefold()
        cancelado = estado in _CANCELADO or estado == 'cancel'
        primer_cierre = operador == 'INTEGRATEL' and bool(str(d.get(normalizar('First Complete Time')) or '').strip())
        completado = (estado in _CERRADO or primer_cierre) and not cancelado
        creado, despacho = instante(text('creado')), instante(text('despacho'))
        cierre = instante(text('cierre')) if completado else None
        sla_txt = text('sla')
        sla = True if sla_txt.casefold() == 'normal' else False if sla_txt.casefold() in ('sla_violation', 'milestone_broken') else None
        if operador == 'PEXT' and completado and creado and cierre:
            # PEXT no trae SLA Status: cumple si se completó dentro de las horas de respuesta (Hrs Respuesta).
            objetivo = _horas(text('objetivo_horas'))
            if objetivo:
                from datetime import datetime
                usado = (datetime.fromisoformat(cierre) - datetime.fromisoformat(creado)).total_seconds() / 3600
                sla, sla_txt = usado <= objetivo, ('normal' if usado <= objetivo else 'sla_violation')
        oficina = text('oficina') or 'Sin oficina'
        causa = text('causa')
        campo_parada, valor_parada = cfg['parada']
        fam = (text('familia') or 'Sin dato') if cfg['familia'] else familia(causa)
        rows.append({
            'id': ticket, 'site': text('site'),
            'oficina': oficina, 'region': _region(operador, oficina), 'contrata': text('contrata') or 'Sin contrata',
            'tecnico': text('tecnico') or 'Sin técnico', 'rm': text('rm'),
            'estado': estado, 'completado': completado, 'cancelado': cancelado,
            'creado': creado, 'despacho': despacho, 'llegada': instante(text('llegada')), 'cierre': cierre,
            # Si no trae fecha de cancelación se usa la del despacho para ubicarla en el tiempo.
            'cancelacion': (instante(text('cancelacion')) or despacho) if cancelado else None,
            'sla': sla, 'sla_texto': sla_txt,
            'parada': str(d.get(normalizar(campo_parada)) or '').strip().casefold() == valor_parada,
            'causa': causa or '(sin causa)', 'familia': fam,
        })
    fechas = [r[k][:10] for r in rows for k in ('creado', 'despacho', 'cierre') if r[k]]
    return {'rows': rows, 'total': len(rows), 'hasta': max(fechas, default=''), 'operador': operador, 'titulo': cfg['titulo'],
            'etiquetas': cfg['etiquetas'], 'con_rm': any(r['rm'] for r in rows), 'con_sla': any(r['sla'] is not None for r in rows),
            'linea_base': LINEA_BASE if operador == 'CLARO' else {}, 'meta_sla': META_SLA, 'meta_eficiencia': META_EFICIENCIA,
            'resumen_familias': operador == 'CLARO'}
