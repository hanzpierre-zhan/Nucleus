# -*- coding: utf-8 -*-
"""Indicadores del flujo de Rendición: dónde se queda cada caso, en cantidad y plata.

Misma arquitectura que el dashboard de Cotizaciones: el servidor encoge cada
fila a un dict ligero ('detalle') y el front recalcula con los filtros activos.
El mapa de estados→pestaña replica el de blueprints/rendicion.py, y hay un test
que verifica que ambos sigan idénticos.
"""
from datetime import datetime
from services.rendicion_estados import estado_de as _estado_de, etapa_de as _etapa_de
from services.normalizacion import primer_texto as _txt
from zoneinfo import ZoneInfo

from services.dashboard_integratel import fecha as _fecha
from services.dashboard_cotizaciones import _money


# ── Estados → pestaña (idéntico a blueprints/rendicion.py::_etapa_de) ────────
ETAPAS = (
    ('VALIDACION', 'Validación'),
    ('DEPOSITOS', 'Depósitos'),
    ('EVIDENCIA', 'Evidencia'),
    ('SUSTENTO', 'Sustento'),
    ('OBSERVADO', 'Observado'),
    ('ATENDIDO', 'Atendido'),
    ('ARCHIVADO', 'Archivar'),
    ('ANULADO', 'Anulado'),
)
ETAPAS_CERRADAS = ('ATENDIDO', 'ARCHIVADO', 'ANULADO')








def _int(v):
    try:
        return int(float(str(v or '0').strip() or 0))
    except ValueError:
        return 0


def indicadores(rows, hoy=None):
    hoy = hoy or datetime.now(ZoneInfo('America/Lima')).date()
    detalle = []
    monto_total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        f_cre = _fecha(row.get('Marca temporal') or row.get('FECHA'))
        etapa = _etapa_de(row)
        solicitado = _money(row.get('Monto total del depósito'))
        pagado = _money(row.get('MONTO PAGO'))
        monto = pagado or solicitado
        monto_total += monto
        detalle.append({
            'key': _txt(row.get('_key')),
            'codigo': _txt(row.get('Número CM / PM / PLM'), row.get('_key')),
            'site': _txt(row.get('Nombre de site')),
            'proyecto': _txt(row.get('Nombre del proyecto')) or 'Sin proyecto',
            'beneficiario': _txt(row.get('Técnico beneficiario')) or 'Sin beneficiario',
            'solicito': _txt(row.get('INTERACCION'), row.get('Responsable de la validación'),
                             row.get('Supervisor encargado')) or 'Sin datos',
            'supervisor': _txt(row.get('Supervisor encargado')) or 'Sin supervisor',
            'estado': _estado_de(row),
            'etapa': etapa,
            'presupuesto': _txt(row.get('Tipo de presupuesto')) or 'Sin tipo',
            'gasto': _txt(row.get('Tipo de gasto')) or 'Sin tipo',
            'monto': monto,
            'solicitado': solicitado,
            'pagado': pagado,
            'mes': f_cre.strftime('%Y-%m') if f_cre else '',
            'dia': f_cre.isoformat()[:10] if f_cre else '',
            'f_pago': _txt(row.get('FECHA PAGO')),
            'f_valid': _txt(row.get('FECHA VALIDACION')),
            'f_sust': _txt(row.get('FECHA SUSTENTO')),
            'valido_por': _txt(row.get('VALIDADO POR')),
            'deposito_por': _txt(row.get('DEPOSITADO POR')),
            'sustento_por': _txt(row.get('SUSTENTADO POR')),
            'rechazo_por': _txt(row.get('RECHAZADO POR'), row.get('DEVUELTO POR')),
            'motivo': _txt(row.get('OBSERVACIONES'), row.get('COMENTARIOS SUSTENTO')),
            'veces_rechazado': _int(row.get('VECES RECHAZADO')),
            'foto_pago': bool(_txt(row.get('FOTO PAGO'))),
            'evidencia_sustento': bool(_txt(row.get('SUSTENTO_CARGAR EVIDENCIAS'),
                                            row.get('SUSTENTO_ADJUNTAR COMPROBANTE'))),
            'aging': (hoy - f_cre).days if (f_cre and etapa not in ETAPAS_CERRADAS) else None,
        })
    return {
        'mes_actual': hoy.strftime('%Y-%m'),
        'hoy': hoy.isoformat(),
        'total': len(detalle),
        'monto_total': round(monto_total, 2),
        'detalle': detalle,
    }
