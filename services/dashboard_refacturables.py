from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import json

from sqlalchemy.orm import selectinload

from models import CajaChicaSolicitud
from services.caja_chica import es_refacturable, pestana_item


def caja_chica():
    from blueprints.caja_chica import _alcance

    alcance = _alcance()
    consulta = CajaChicaSolicitud.query.filter(
        CajaChicaSolicitud.estado != 'ELIMINADO'
    ).options(selectinload(CajaChicaSolicitud.items))
    if alcance is not None:
        consulta = consulta.filter(CajaChicaSolicitud.proyecto.in_(alcance))
    filas = []
    for solicitud in consulta.order_by(CajaChicaSolicitud.id.desc()).yield_per(500):
        historial = json.loads(solicitud.historial or '[]')
        formulario = next((e['formulario'] for e in reversed(historial) if 'formulario' in e), {})
        estados = defaultdict(lambda: defaultdict(Decimal))
        conceptos = defaultdict(int)
        for item in solicitud.items:
            tipo = 'Refacturable' if es_refacturable(solicitud, item) else 'Gasto Cobra'
            estados[tipo][pestana_item(solicitud, item)] += item.monto
            conceptos[item.tipo_gasto] += 1
        if estados:
            filas.append({
                'codigo': solicitud.codigo,
                'proyecto': solicitud.proyecto,
                'responsable': solicitud.tecnico,
                'fecha': (solicitud.creado - timedelta(hours=5)).date().isoformat(),
                'cancelada': solicitud.estado in ('ANULADO', 'CANCELADO'),
                'supervisor': formulario.get('supervisor') or 'Sin supervisor',
                'conceptos': dict(conceptos),
                'gastos': {tipo: {etapa: int(monto * 100) for etapa, monto in etapas.items()}
                           for tipo, etapas in estados.items()},
            })
    return filas
