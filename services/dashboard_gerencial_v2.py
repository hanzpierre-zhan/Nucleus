"""Dashboard gerencial: operación FLM (SLA y backlog), plata en la calle (Caja Chica),
embudo de cotizaciones y alertas para gestionar hoy.

Usa las mismas reglas que cada módulo: el SLA sale de la página SLA (blueprints.sla.casos),
Caja Chica de sus tablas y Cotizaciones de su módulo (nucleus_data)."""
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

PERIODOS = {'mes': 'Este mes', 'anterior': 'Mes anterior', '7': 'Últimos 7 días', 'hoy': 'Hoy'}
META_SLA = 95
_SIN_WO = {'', '-', '--', '—', 'NO TIENE', 'NO APLICA', 'N/A', 'NA', 'PENDIENTE', 'SIN WO', 'CM PENDIENTE', 'POR DEFINIR'}


def _hoy():
    return (datetime.utcnow() - timedelta(hours=5)).date()


def rango(periodo, hoy=None):
    hoy = hoy or _hoy()
    if periodo == 'hoy':
        return hoy, hoy
    if periodo == '7':
        return hoy - timedelta(days=6), hoy
    inicio_mes = hoy.replace(day=1)
    if periodo == 'anterior':
        fin = inicio_mes - timedelta(days=1)
        return fin.replace(day=1), fin
    return inicio_mes, hoy


def _num(valor):
    try:
        return Decimal(re.sub(r'[^0-9.\-]', '', str(valor or '')) or '0')
    except InvalidOperation:
        return Decimal('0')


def _f(valor):
    return float(round(Decimal(valor or 0), 2))


def _operacion(menu, desde, hasta):
    """SLA de los cerrados del periodo y backlog de hoy por FLM (mismas reglas que la página SLA)."""
    from blueprints import sla
    from models import Proyecto
    ahora = datetime.utcnow() - timedelta(hours=5)
    salida = []
    for clave, nombre_modulo, nombre, color in sla.PROYECTOS:
        if nombre_modulo not in menu or clave not in sla.CON_CRITERIOS:
            continue
        modulo = Proyecto.query.filter_by(nombre=nombre_modulo).first()
        if not modulo:
            continue
        casos = sla.casos(modulo)
        cerrados = [c for c in casos if c['cerrado'] and c['fin'] and desde.isoformat() <= c['fin'][:10] <= hasta.isoformat()]
        medidos = [c for c in cerrados if c.get('sla_status')]
        ok = sum(1 for c in medidos if c['sla_status'] == 'normal')
        abiertos = [c for c in casos if not c['cerrado']]
        vencidos = []
        for c in abiertos:
            if not c.get('objetivo') or not c.get('inicio'):
                continue
            try:
                inicio = datetime.strptime(c['inicio'][:19], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
            resto = c['objetivo'] - ((ahora - inicio).total_seconds() / 60 - (c.get('pausa') or 0))
            if resto < 0:
                vencidos.append({'ticket': c['ticket'], 'site': c.get('site', ''), 'tecnico': c.get('fme') or c.get('tecnico_nombre') or c.get('tecnico') or '',
                                 'proyecto': nombre, 'horas': round(-resto / 60, 1)})
        salida.append({'clave': clave, 'nombre': nombre, 'color': color, 'url': '/analytics/' + clave.lower(),
                       'cerrados': len(cerrados), 'medidos': len(medidos), 'ok': ok,
                       'sla': round(ok / len(medidos) * 100, 1) if medidos else None,
                       'backlog': len(abiertos), 'vencidos': vencidos})
    return salida


def _caja_chica(hoy):
    """Lo depositado y aún no cerrado: por rendir (con antigüedad), en revisión, rechazado sin corregir y rendido."""
    from models import CajaChicaItem, CajaChicaSolicitud
    filas = (CajaChicaItem.query.join(CajaChicaSolicitud, CajaChicaSolicitud.id == CajaChicaItem.solicitud_id)
             .filter(CajaChicaSolicitud.estado == 'DEPOSITADO')
             .with_entities(CajaChicaItem.estado, CajaChicaItem.monto, CajaChicaItem.monto_gastado,
                            CajaChicaSolicitud.id, CajaChicaSolicitud.codigo, CajaChicaSolicitud.tecnico,
                            CajaChicaSolicitud.proyecto, CajaChicaSolicitud.depositado_en).all())
    total = {'por_rendir': Decimal(0), 'rechazado': Decimal(0), 'en_revision': Decimal(0), 'rendido': Decimal(0)}
    cuenta = defaultdict(int)
    sol_rechazo = set()
    tramos = [['0–7 días', 0, 7, Decimal(0), 0], ['8–15 días', 8, 15, Decimal(0), 0], ['16–30 días', 16, 30, Decimal(0), 0], ['Más de 30 días', 31, 10 ** 6, Decimal(0), 0]]
    tecnicos = defaultdict(lambda: {'monto': Decimal(0), 'gastos': 0, 'dias': 0, 'solicitudes': set(), 'proyecto': ''})
    dias_total = dias_n = 0
    for estado, monto, gastado, sid, codigo, tecnico, proyecto, depositado_en in filas:
        monto = Decimal(monto or 0)
        if estado == 'POR_RENDIR':
            dias = (hoy - (depositado_en - timedelta(hours=5)).date()).days if depositado_en else 0
            total['por_rendir'] += monto; cuenta['por_rendir'] += 1; dias_total += dias; dias_n += 1
            for t in tramos:
                if t[1] <= dias <= t[2]:
                    t[3] += monto; t[4] += 1
            x = tecnicos[tecnico]
            x['monto'] += monto; x['gastos'] += 1; x['dias'] = max(x['dias'], dias); x['solicitudes'].add(codigo); x['proyecto'] = proyecto
        elif estado == 'RECHAZADO':
            total['rechazado'] += monto; cuenta['rechazado'] += 1; sol_rechazo.add(sid)
        elif estado == 'EN_REVISION':
            total['en_revision'] += Decimal(gastado or monto); cuenta['en_revision'] += 1
        elif estado in ('APROBADO', 'DEVUELTO'):
            total['rendido'] += Decimal(gastado or 0); cuenta['rendido'] += 1
    atrasados = sorted(({'tecnico': k, 'monto': _f(v['monto']), 'gastos': v['gastos'], 'dias': v['dias'], 'proyecto': v['proyecto'],
                         'solicitudes': ', '.join(sorted(v['solicitudes'])[:4]) + (' …' if len(v['solicitudes']) > 4 else '')}
                        for k, v in tecnicos.items() if v['dias'] > 15), key=lambda x: (-x['dias'], -x['monto']))
    return {'total': {k: _f(v) for k, v in total.items()}, 'cuenta': dict(cuenta), 'solicitudes_con_rechazo': len(sol_rechazo),
            'dias_promedio': round(dias_total / dias_n) if dias_n else 0,
            'antiguedad': [{'tramo': t[0], 'monto': _f(t[3]), 'gastos': t[4]} for t in tramos],
            'atrasados': atrasados}


def _cotizaciones(hoy):
    """Embudo (monto y cantidad por estado) y alertas: en Cliente hace +7 días, aprobadas sin WO, sustento aprobado sin fotos."""
    from models import NucleusData, Proyecto
    modulo = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not modulo:
        return None
    etapas = [('En Aprobación', 'En Cliente'), ('Aprobado', 'Aprobadas'), ('Atendido', 'Atendidas'), ('Validado', 'Validadas')]
    embudo = {e: {'etapa': t, 'monto': Decimal(0), 'cantidad': 0} for e, t in etapas}
    en_cliente, sin_wo, sin_fotos = [], [], []
    for clave, crudo in NucleusData.query.filter_by(proyecto_id=modulo.id).with_entities(NucleusData.key_value, NucleusData.data_json):
        try:
            d = json.loads(crudo or '{}')
        except ValueError:
            continue
        estado = str(d.get('ESTADO COTIZACION') or '').strip()
        monto = _num(d.get('SUB TOTAL + FEE'))
        if estado in embudo:
            embudo[estado]['monto'] += monto; embudo[estado]['cantidad'] += 1
        fila = {'cotizacion': clave, 'cliente': d.get('CLIENTE') or '', 'monto': _f(monto), 'gestor': d.get('GESTOR') or '',
                'wo': d.get('NUMERO WO') or '', 'fecha': str(d.get('FECHA') or '')[:10]}
        if estado == 'En Aprobación':
            try:
                dias = (hoy - date.fromisoformat(fila['fecha'])).days
            except ValueError:
                dias = None
            if dias is not None and dias > 7:
                en_cliente.append({**fila, 'dias': dias})
        if estado == 'Aprobado' and str(d.get('NUMERO WO') or '').strip().upper() in _SIN_WO:
            sin_wo.append(fila)
        if str(d.get('_SUSTENTO_APROBADO') or '') == '1':
            fichas = d.get('_SUSTENTO_FICHAS') or {}
            fotos = sum(len(g) for f in fichas.values() if isinstance(f, dict) for g in (f.get('item_photos') or {}).values() if isinstance(g, list))
            fotos += sum(1 for f in fichas.values() if isinstance(f, dict) and f.get('location_picture'))
            if not fotos and not str(d.get('FOTOS SUSTENTO') or '').strip():
                sin_fotos.append(fila)
    return {'embudo': [{**v, 'monto': _f(v['monto'])} for v in embudo.values()],
            'en_cliente': sorted(en_cliente, key=lambda x: -x['dias']), 'sin_wo': sin_wo, 'sin_fotos': sin_fotos}


def resumen(proyectos, periodo='mes', hoy=None):
    hoy = hoy or _hoy()
    periodo = periodo if periodo in PERIODOS else 'mes'
    desde, hasta = rango(periodo, hoy)
    menu = {p.nombre for p in proyectos}
    operacion = _operacion(menu, desde, hasta)
    caja = _caja_chica(hoy) if 'Caja Chica' in menu else None
    cot = _cotizaciones(hoy) if 'Cotizaciones' in menu else None
    vencidos = sorted((v for o in operacion for v in o['vencidos']), key=lambda x: -x['horas'])
    for o in operacion:
        o['vencidos'] = len(o['vencidos'])
    return {'periodo': periodo, 'periodos': PERIODOS, 'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'meta_sla': META_SLA,
            'operacion': operacion, 'caja': caja, 'cotizaciones': cot, 'vencidos': vencidos[:300], 'total_vencidos': len(vencidos)}
