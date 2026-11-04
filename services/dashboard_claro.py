"""Lectura de tickets Claro: conserva los datos fuente y explicita los faltantes."""
from datetime import datetime
from services.dashboard_integratel import normalizar


def instante(value):
    value=str(value or '').strip()
    if not value:return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).replace(tzinfo=None).isoformat()
    except ValueError:pass
    for fmt in ('%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M','%d/%m/%Y'):
        try:return datetime.strptime(value,fmt).isoformat()
        except ValueError:pass
    return None


def indicadores(registros):
    rows=[];sin_id=0
    for raw in registros:
        d={normalizar(k):v for k,v in raw.items()}
        def text(*keys):
            return next((str(d[normalizar(k)]).strip() for k in keys if str(d.get(normalizar(k)) or '').strip()),'')
        ticket=text('Ticket Id')
        if not ticket:
            sin_id+=1;continue
        estado=text('Task Status').casefold()
        sla=text('SLA Status').casefold()
        rows.append({'id':ticket,'tipo':text('Task Type') or ticket.split('-')[0],
            'estado':estado,'creacion':instante(text('Create Time')),
            'cierre':instante(text('Complete Time')) if estado in ('completed','closed','complete','close') else None,
            'cancelacion':instante(text('Cancel Time')) if estado in ('canceled','cancelled') else None,
            'cancelado':estado in ('canceled','cancelled'),
            'completado':estado in ('completed','closed','complete','close'),
            'despacho':instante(text('Dispatch Time')),
            'sla':True if sla=='normal' else False if sla in ('sla_violation','milestone_broken') else None,
            'zona':text('FM Office','FM  Office Site') or 'Sin oficina',
            'fme':text('Assign To FME Full Name','Assign To FME') or 'Sin FME',
            'categoria':text('Task Category') or 'Sin categoría',
            'site':text('Site Name','Site ID') or 'Sin site'})
    fechas=[r['creacion'][:10] for r in rows if r['creacion']]
    ultimas=[r[k][:10] for r in rows for k in ('creacion','cierre','cancelacion','despacho') if r[k]]
    return {'rows':rows,'sin_identificador':sin_id,'desde':min(fechas,default=''),
            'hasta':max(ultimas,default=''),'total':len(rows)}
