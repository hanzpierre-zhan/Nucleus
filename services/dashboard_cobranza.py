# -*- coding: utf-8 -*-
"""Indicadores del Cuadro de Control de Cobranza.

Reutiliza el catálogo que ya consolida el módulo Refacturable
(blueprints/refacturable.py::_registros): una fila por cotización aprobada, ya
cruzada con los FLM (cliente ENTEL / CLARO / INTEGRATEL) y con el seguimiento
manual (monto_cobra, numero_expense, mes_cierre, ...).

Misma arquitectura que los otros dashboards: el servidor encoge cada fila a un
dict ligero ('detalle') y el front recalcula con los filtros activos. Aquí el
extra es que los importes viven en la tabla de seguimiento, no en el JSON, así
que el servicio normaliza cantidad y plata en un solo lugar.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from services.dashboard_cotizaciones import _money

CLIENTES = ('ENTEL', 'CLARO', 'INTEGRATEL')


def _cliente(nombre):
    """Convierte 'CLARO, ENTEL' en un cliente canónico.

    Una cotización puede cruzar varias WOs de distinto operador. Para no
    duplicar plata se asigna íntegra al bucket 'MIXTO' cuando aparece más de
    un operador, y al operador único cuando solo hay uno.
    """
    texto = str(nombre or '').upper()
    hallados = [c for c in CLIENTES if c in texto]
    if len(hallados) == 1:
        return hallados[0]
    if len(hallados) > 1:
        return 'MIXTO'
    limpio = str(nombre or '').strip()
    return limpio.upper() if limpio else 'SIN CLIENTE'


def _tiene_evidencia(fotos):
    if not isinstance(fotos, dict):
        return False
    return any(bool(v) for v in fotos.values())


def indicadores(registros, hoy=None):
    """Devuelve {'total', 'monto_total', 'mes_actual', 'hoy', 'detalle': [...]}."""
    hoy = hoy or datetime.now(ZoneInfo('America/Lima')).date()
    detalle = []
    monto_total = 0.0
    for row in registros or []:
        if not isinstance(row, dict):
            continue
        # El monto a cobrar es manual (monto_cobra); mientras no se declare se
        # usa el monto de la cotización (monto_hw) para que la plata del tablero
        # tenga sentido desde el primer día.
        monto_hw = _money(row.get('monto_hw'))
        monto_cobra = _money(row.get('monto_cobra'))
        monto = monto_cobra if monto_cobra > 0 else monto_hw
        monto_total += monto
        documentos = row.get('documentos') or {}
        numero_expense = str(row.get('numero_expense') or '').strip()
        mes_cierre = str(row.get('mes_cierre') or '').strip()
        avance = int(row.get('avance') or 0)
        detalle.append({
            'id': row.get('id'),
            'cotizacion': str(row.get('cotizacion') or ''),
            'correlativo': str(row.get('correlativo') or ''),
            'cliente': _cliente(row.get('nombre_proyecto')),
            'gestor': str(row.get('gestor') or ''),
            'wo': str(row.get('numero_wo') or ''),
            'monto': round(monto, 2),
            'monto_hw': round(monto_hw, 2),
            'monto_cobra': round(monto_cobra, 2),
            'monto_manual': monto_cobra > 0,
            'margen': round(monto - monto_hw, 2),
            'avance': avance,
            'completo': avance >= 100,
            'con_evidencia': _tiene_evidencia(row.get('fotos')),
            'completos': sum(1 for v in documentos.values() if v == 'Completo'),
            'pendientes': sum(1 for v in documentos.values() if v == 'Pendiente'),
            'no_aplica': sum(1 for v in documentos.values() if v == 'No aplica'),
            'numero_expense': numero_expense,
            'con_expense': bool(numero_expense),
            'mes_cierre': mes_cierre if len(mes_cierre) >= 7 else '',
            'estado_cotizacion': str(row.get('estado_cotizacion') or ''),
            'estatus': str(row.get('estatus') or ''),
            'estado_liquidacion': str(row.get('estado_liquidacion') or ''),
        })
    return {
        'mes_actual': hoy.strftime('%Y-%m'),
        'hoy': hoy.isoformat(),
        'total': len(detalle),
        'monto_total': round(monto_total, 2),
        'detalle': detalle,
    }
