"""Dashboard operativo FLM (Claro, Integratel y Entel) con el mismo formato.

Lee los tickets tal cual vienen y los lleva a una misma forma. Lo que no viene
en la data se deja vacío (no se inventa SLA ni cierre).

Columnas por proyecto:
  Claro:      Ticket Id · Create Time · Dispatch Time · Complete Time · SLA Status · FM Office · FME Contractor
  Integratel: Task Id · Createtime · Dispatch Time · First Complete Time · Sla Status · Fm Office · FME contrator
  Entel:      Task ID(create) · CreateTime(create) · dispatch_time · SubmitTime(complete) · SLA Status · fm_office · Contractor
"""
import re

from services.dashboard_integratel import instante, normalizar

_CERRADO = ('completed', 'closed', 'complete', 'close')
_CANCELADO = ('canceled', 'cancelled')
_TAREA = re.compile(r'^(CM|PM|PLM)-', re.I)

CAMPOS = {
    'CLARO': {
        'id': ('Ticket Id',), 'tipo': ('Task Type',), 'estado': ('Task Status',),
        'creacion': ('Create Time',), 'despacho': ('Dispatch Time',), 'cierre': ('Complete Time',),
        'cancelacion': ('Cancel Time', '_fecha_cancel_reject', 'FECHA CAMBIO ESTADO'),
        'sla': ('SLA Status',), 'zona': ('FM Office', 'FM  Office Site'), 'proveedor': ('FME Contractor',),
        'fme': ('Assign To FME Full Name', 'Assign To FME'), 'rm': (), 'categoria': ('Task Category',),
        'site': ('Site Name', 'Site ID'), 'asociado': ('associateorderid',),
    },
    'INTEGRATEL': {
        'id': ('Task Id',), 'tipo': ('Task Type',), 'estado': ('Task Status',),
        'creacion': ('Createtime', 'Create Time'), 'despacho': ('Dispatch Time',),
        # El SLA termina en el primer cierre (si lo reabren no cuenta).
        'cierre': ('First Complete Time', 'Complete Time'),
        'cancelacion': ('Cancel Time', 'FECHA CAMBIO ESTADO'),
        'sla': ('Sla Status', 'SLA Status'), 'zona': ('Fm Office',), 'proveedor': ('FME contrator',),
        'fme': ('Assign To Fme Full Name', 'Assign To Fme'), 'rm': (), 'categoria': ('Task Category',),
        'site': ('Site Id Name', 'Site Id'), 'asociado': (),
    },
    'ENTEL': {
        'id': ('Task ID(create)', 'id', 'Ticket ID'), 'tipo': (), 'estado': ('Ticket Status', 'Estado de la tarea (WO State)'),
        'creacion': ('CreateTime(create)',), 'despacho': ('dispatch_time',), 'cierre': ('SubmitTime(complete)', 'complete_time'),
        'cancelacion': ('Cancel Time',),
        'sla': ('SLA Status',), 'zona': ('fm_office',), 'proveedor': ('Contractor',),
        'fme': ('assign_to_fme',), 'rm': ('Region Manager(create)',), 'categoria': ('Task Category(create)',),
        'site': ('Site ID(create)',), 'asociado': ('Associate OrderId',),
    },
}


def region(oficina):
    """Región a partir de la oficina: 'HUAWEI CENTRO ICA' → CENTRO, 'ICA_REGIÓN SUR' → SUR, 'FM Office LIMA SUR' → LIMA."""
    texto = normalizar(oficina).upper()
    m = re.search(r'REGION(NORTE|SUR|CENTRO|ORIENTE|LIMA)', texto)
    if m:
        return m[1]
    for nombre in ('LIMA', 'CENTRO', 'NORTE', 'SUR', 'ORIENTE'):
        if nombre in texto:
            return nombre
    return 'Sin región'


def indicadores(registros, operador='CLARO'):
    campos = CAMPOS[operador]
    rows = []
    sin_id = 0
    for raw in registros:
        d = {normalizar(k): v for k, v in raw.items()}

        def text(clave):
            return next((str(d[normalizar(k)]).strip() for k in campos[clave] if str(d.get(normalizar(k)) or '').strip()), '')

        ticket = text('id')
        if not ticket:
            sin_id += 1
            continue
        estado = text('estado').casefold()
        cancelado = estado in _CANCELADO
        primer_cierre = operador == 'INTEGRATEL' and bool(str(d.get(normalizar('First Complete Time')) or '').strip())
        completado = (estado in _CERRADO or primer_cierre) and not cancelado
        sla = text('sla').casefold()
        tipo = (text('tipo') or ticket.split('-')[0]).upper()
        asociado = text('asociado')
        zona = text('zona') or 'Sin oficina'
        rows.append({
            'id': ticket, 'tipo': tipo if tipo in ('CM', 'PM', 'PLM') else (tipo or 'Sin tipo'),
            'estado': estado, 'creacion': instante(text('creacion')),
            'cierre': instante(text('cierre')) if completado else None,
            'cancelacion': instante(text('cancelacion')) if cancelado else None,
            'cancelado': cancelado, 'completado': completado,
            'despacho': instante(text('despacho')),
            # milestone_broken también es incumplimiento (igual que en la página SLA).
            'sla': True if sla == 'normal' else False if sla in ('sla_violation', 'milestone_broken') else None,
            'zona': zona, 'region': region(zona),
            'proveedor': text('proveedor') or 'Sin proveedor',
            'rm': text('rm'),
            'fme': text('fme') or 'Sin FME',
            'categoria': text('categoria') or 'Sin categoría',
            'site': text('site') or 'Sin site',
            # Hijo: el ticket está asociado a otra tarea (CM/PM/PLM), no a un incidente.
            'hijo': any(_TAREA.match(p.strip()) and p.strip() != ticket for p in re.split(r'[;,]', asociado)),
        })
    fechas = [r['creacion'][:10] for r in rows if r['creacion']]
    ultimas = [r[k][:10] for r in rows for k in ('creacion', 'cierre', 'cancelacion', 'despacho') if r[k]]
    return {'rows': rows, 'sin_identificador': sin_id, 'desde': min(fechas, default=''),
            'hasta': max(ultimas, default=''), 'total': len(rows), 'operador': operador,
            'con_rm': any(r['rm'] for r in rows)}
