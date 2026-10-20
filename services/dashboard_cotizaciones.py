# -*- coding: utf-8 -*-
"""Indicadores del pipeline comercial de Cotizaciones.

Misma arquitectura que el dashboard operativo: el servidor encoge cada fila
del módulo a un dict ligero ('detalle') y el front recalcula TODAS las métricas
con los filtros activos (mes, día, cliente, tipo, solicitante), así un cambio
de filtro no recarga la página.

Solo lee: nunca modifica datos.
"""
import re
from services.normalizacion import primer_texto as _txt
from datetime import datetime
from zoneinfo import ZoneInfo

from services.dashboard_integratel import fecha as _fecha
from services.dashboard_consulta import comunes, valor, proyecto, dia, validacion_sustento, espera, gasto


# ── Pestaña de la fila — idéntico a blueprints/cotizacion.py ─────────────────
# Cualquier desalineación entre ambos mapas ya se detectó como bug del flujo;
# aquí se replica el mapa del BACKEND (la fuente de verdad de las pestañas).
MAPA_PESTANIA = {
    'atendido': 'atendido', 'validado': 'atendido',
    'cotizado': 'cliente', 'en aprobación': 'cliente', 'en aprobacion': 'cliente',
    'aprobado': 'sustentar', 'sustentar': 'sustentar',
    'cancelado': 'cancelado', 'anulado': 'cancelado', 'anulada': 'cancelado',
}

PESTANIAS = ('registro', 'cliente', 'sustentar', 'atendido', 'cancelado')


def _pestania(d):
    v = str(d.get('ESTADO COTIZACION') or '').strip().lower()
    return MAPA_PESTANIA.get(v, 'registro')


def _en_proveedor(d):
    """Solo aprobadas con pago a proveedor, independientemente del presupuesto."""
    p = _pestania(d)
    return (str(d.get('TIPO GASTO APROBACION') or '').strip().casefold() == 'proveedor'
            and p in ('sustentar', 'atendido'))


def _money(value):
    """'S/ 1,234.56' | '1,234.56' | '1.234,56' | '1050.00' | None -> float."""
    text = str(value or '').strip()
    if not text:
        return 0.0
    text = re.sub(r'[Ss]/\s*', '', text)
    text = re.sub(r'[^\d,.\-]', '', text)
    if ',' in text and '.' in text:
        if text.rfind(',') < text.rfind('.'):
            text = text.replace(',', '')           # miles: 1,234.56
        else:
            text = text.replace('.', '').replace(',', '.')  # 1.234,56
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return 0.0




def _flag(v):
    return str(v or '').strip() == '1'


def indicadores(rows, hoy=None):
    """Devuelve {'total', 'monto_total', 'mes_actual', 'hoy', 'detalle': [...]}."""
    hoy = hoy or datetime.now(ZoneInfo('America/Lima')).date()
    detalle = []
    monto_total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        gestor = _txt(row.get('GESTOR'))
        f_cre = _fecha(row.get('FECHA'))
        f_cot = _fecha(row.get('FECHA COTIZADO'))
        f_apr = _fecha(row.get('FECHA APROBACION'))
        f_ate = _fecha(row.get('FECHA ATENCION'))
        pest = _pestania(row)
        estado = str(row.get('ESTADO COTIZACION') or '').strip()
        monto = _money(row.get('SUB TOTAL + FEE'))
        monto_total += monto
        detalle.append({
            **comunes(row),
            **espera(row, hoy, {'registro': ['FECHA'] if estado.lower().startswith('pdt') else [],
                              'cliente': ['FECHA ENVIO CLIENTE', 'FECHA COTIZADO'],
                              'sustentar': ['FECHA APROBACION'], 'atendido': ['FECHA ATENCION']}.get(pest, []), cerrado=pest in ('atendido', 'cancelado')),
            'cerrado': pest in ('atendido', 'cancelado'),
            'n': _txt(row.get('N° COTIZACION'), row.get('_key')),
            'key': _txt(row.get('_key')),
            'cliente': _txt(row.get('CLIENTE')) or 'Sin cliente',
            'proyecto': _txt(row.get('NOMBRE DE PROYECTO'), row.get('NOMBRE PROYECTO'), row.get('PROYECTO'), row.get('CLIENTE')) or 'Sin proyecto',
            'gasto': gasto(row.get('TIPO DE GASTO'), 'Sin clasificar'),
            'gasto_aprobacion': gasto(row.get('TIPO GASTO APROBACION'), 'Sin definir'),
            'proyecto_familia': proyecto(valor(row, 'CLIENTE', 'PROYECTO')),
            'situacion': ('Sustentado · validado y atendido' if pest == 'atendido' and validacion_sustento(row)
                         else 'Atendido · sin validación de sustento registrada' if pest == 'atendido'
                         else 'Sustento validado · pendiente de cierre' if pest == 'sustentar' and validacion_sustento(row)
                         else 'Aprobado · sustento sin validación registrada' if pest == 'sustentar'
                         else 'En aprobación · pendiente del cliente' if pest == 'cliente'
                         else 'Anulado' if pest == 'cancelado' else 'Registro'),
            'site': _txt(row.get('NOMBRE SITE')),
            'tipo': _txt(row.get('TIPO DE COTIZACION')) or 'Sin tipo',
            'gestor': gestor or 'Sin gestor',
            'solicito': _txt(row.get('SOLICITADO POR'), gestor) or 'Sin datos',
            'genero': _txt(row.get('COTIZADO POR'), row.get('ENVIADO POR'), gestor) or 'Sin datos',
            'atendido_por': _txt(row.get('ATENDIDO POR')),
            'estado': estado or '(sin estado)',
            'pestania': pest,
            'proveedor': _en_proveedor(row),
            'generada': _flag(row.get('GENERADA')),
            'monto': monto,
            'monto_registrado': bool(str(row.get('SUB TOTAL + FEE') if row.get('SUB TOTAL + FEE') is not None else '').strip()),
            'facturado_registrado': bool(str(row.get('SUBTOTAL FACTURA PROVEEDOR') if row.get('SUBTOTAL FACTURA PROVEEDOR') is not None else '').strip()),
            'facturado': _money(row.get('SUBTOTAL FACTURA PROVEEDOR')),
            'mes': f_cre.strftime('%Y-%m') if f_cre else '',
            'dia': f_cre.isoformat()[:10] if f_cre else '',
            'dia_solicitud': f_cre.isoformat()[:10] if f_cre else '',
            'dia_cotizacion': dia(row.get('FECHA COTIZADO')),
            'dia_aprobacion': dia(row.get('FECHA APROBACION')),
            'dia_atencion': dia(row.get('FECHA ATENCION')),
            'f_cot': f_cot.isoformat() if f_cot else '',
            'f_apr': f_apr.isoformat() if f_apr else '',
            'f_ate': f_ate.isoformat() if f_ate else '',
            'mes_ate': f_ate.strftime('%Y-%m') if f_ate else '',
            # Aging solo tiene sentido en Sustentar (aprobada sin atender).
            'aging': (hoy - f_apr).days if (pest == 'sustentar' and f_apr) else None,
            'sustento_ok': validacion_sustento(row),
            'factura_ok': bool(_txt(row.get('ADJUNTO FACTURA PROVEEDOR'))),
            'cotprov_ok': bool(_txt(row.get('ADJUNTO COTIZACION PROVEEDOR'))),
            'correo_ok': bool(_txt(row.get('ADJUNTO CORREO CLIENTE'))),
            'oc_prov': _txt(row.get('NUMERO OC PROVEEDOR')),
            'fac_num': _txt(row.get('NUMERO FACTURA PROVEEDOR')),
            'wo': _txt(row.get('NUMERO WO')),
            'motivo_rechazo': _txt(row.get('MOTIVO RECHAZO')),
            'motivo_cancel': _txt(row.get('MOTIVO CANCELACION')),
        })
    return {
        'mes_actual': hoy.strftime('%Y-%m'),
        'hoy': hoy.isoformat(),
        'total': len(detalle),
        'monto_total': round(monto_total, 2),
        'detalle': detalle,
        'ingreso_disponible': False,
    }
