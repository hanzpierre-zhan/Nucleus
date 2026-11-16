"""SLA: cumplimiento de los tickets FLM (CM, PM y PLM) por proyecto.

Reglas:
- CM cuenta desde Dispatch Time; PM y PLM desde Arrive Time.
- Abierto: se calcula contra la hora actual. Cerrado (Task Status completed o closed): termina en la fecha y
  hora en que cambió a completed (Complete Time; si falta, FECHA CAMBIO ESTADO).
- Canceled no se mide.
- Objetivo: SLA Hour (minutos). Resultado de un cerrado: SLA Status ("normal" cumple; "sla_violation" no).
- Abiertos: vencido, por vencer (queda ≤ 25 % del objetivo o ≤ 60 min) o en plazo.
- Técnico: Schedule Operator.

Entel (KPI OM Sitios):
- Desde dispatch_time hasta SubmitTime(complete) (o complete_time), menos Total SLA Pause Duration (segundos).
- Objetivo según Fault Level: Crítica/Critical 4 h · Alta/Major 4 h · Media 6 h · Baja/Minor 48 h · Calidad 30 días.
- Cumplimiento según SLA Status; "SLA Cobra" es el cálculo propio para contrastarlo.
- Técnico: assign_to_fme.
"""
import json
import re

from flask import Blueprint, abort, jsonify, render_template, session

from models import NucleusData, Proyecto
from services import get_menu_proyectos, login_required

bp = Blueprint('sla', __name__)

PROYECTOS = (('CLARO', 'FLM - CLARO', 'Claro', '#dc2626'), ('ENTEL', 'FLM - ENTEL', 'Entel', '#1d4ed8'),
             ('INTEGRATEL', 'FLM - INTEGRATEL', 'Integratel', '#16a34a'), ('PEXT', 'FLM - PEXT', 'PEXT', '#ea580c'))
# Proyectos con criterios de SLA definidos (los demás se muestran como "por definir").
CON_CRITERIOS = {'CLARO', 'ENTEL'}
POR_VENCER_PORCENTAJE = 0.25
POR_VENCER_MINUTOS = 60


def _permitidos():
    """Proyectos FLM que el usuario puede ver (los mismos de su menú)."""
    menu = {p.nombre for p in get_menu_proyectos(session.get('user_id'), session.get('rol'))}
    return [p for p in PROYECTOS if p[1] in menu]


def _tipo(datos, clave):
    tipo = str(datos.get('Task Type') or '').strip().upper()
    if tipo in ('CM', 'PM', 'PLM'):
        return tipo
    m = re.match(r'(CM|PLM|PM)\b|^(CM|PLM|PM)-', str(clave or '').upper())
    return (m.group(1) or m.group(2)) if m else ''


def _minutos(valor):
    try:
        n = float(str(valor or '').strip())
    except ValueError:
        return None
    return int(n) if n > 0 else None


# Objetivo de Entel en horas según Fault Level (llaves en minúscula y sin tilde).
OBJETIVO_ENTEL = {'critica': 4, 'critical': 4, 'alta': 4, 'major': 4, 'media': 6, 'baja': 48, 'minor': 48, 'calidad': 720}


def _plano(texto):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto or '')) if unicodedata.category(c) != 'Mn').strip().lower()


def _fecha(texto):
    from datetime import datetime
    try:
        return datetime.strptime(str(texto or '').strip()[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def _caso_entel(d, clave):
    """Un ticket de Entel con los mismos campos que usa la página para Claro."""
    estado = str(d.get('Ticket Status') or '').strip()
    if 'cancel' in estado.lower():
        return None
    nivel = str(d.get('Fault Level(create)') or d.get('Fault Level') or '').strip()
    horas = OBJETIVO_ENTEL.get(_plano(nivel))
    inicio = str(d.get('dispatch_time') or '').strip()[:19]
    fin = str(d.get('SubmitTime(complete)') or d.get('complete_time') or '').strip()[:19]
    try:
        pausa = max(0.0, float(str(d.get('Total SLA Pause Duration') or '0').strip() or 0)) / 60
    except ValueError:
        pausa = 0.0
    cerrado = bool(re.search(r'complet|close', estado.lower()))
    objetivo = horas * 60 if horas else None
    # SLA Cobra: tiempo neto (sin parada de reloj) contra el objetivo del Fault Level.
    cobra = ''
    ini_d, fin_d = _fecha(inicio), _fecha(fin)
    if cerrado and ini_d and fin_d and objetivo:
        neto = (fin_d - ini_d).total_seconds() / 60 - pausa
        cobra = 'sla_violation' if neto > objetivo else 'normal'
    tecnico = str(d.get('assign_to_fme') or '').strip()
    return {
        'ticket': str(d.get('Ticket ID') or clave), 'tipo': _tipo(d, clave) or 'CM', 'site': str(d.get('Site Name(create)') or ''),
        'tecnico': tecnico, 'tecnico_nombre': '', 'estado_ticket': estado,
        'inicio': inicio, 'fin': fin if cerrado else '', 'cerrado': cerrado,
        'dispatch': inicio, 'arrive': str(d.get('arrive_time') or '').strip()[:19],
        'sla_hour': (nivel + ' · ' + (f'{horas // 24} días' if horas and horas >= 720 else f'{horas} h')) if horas else (nivel or ''),
        'categoria': str(d.get('Task Category(create)') or '').strip(), 'sla_status_original': str(d.get('SLA Status') or '').strip(),
        'objetivo': objetivo, 'sla_status': str(d.get('SLA Status') or '').strip().lower(),
        'prioridad': nivel, 'pausa': round(pausa, 1), 'sla_cobra': cobra,
    }


def casos(proyecto):
    """Casos del proyecto con lo necesario para el SLA (sin cancelados)."""
    filas = (NucleusData.query.filter_by(proyecto_id=proyecto.id)
             .with_entities(NucleusData.key_value, NucleusData.data_json))
    nombres, salida = {}, []
    es_entel = proyecto.nombre == 'FLM - ENTEL'
    for clave, crudo in filas:
        try:
            d = json.loads(crudo or '{}')
        except ValueError:
            continue
        if es_entel:
            caso = _caso_entel(d, clave)
            if caso:
                salida.append(caso)
            continue
        # Nombre de cada código de técnico, tomado de las columnas que traen ambos.
        for codigo, nombre in ((d.get('Create Operator ID'), d.get('Create Operator')),
                               (d.get('Assign To FME'), d.get('Assign To FME Full Name'))):
            codigo, nombre = str(codigo or '').strip(), str(nombre or '').strip()
            if re.fullmatch(r'[A-Z]\d{5,}', codigo) and nombre and not re.fullmatch(r'[A-Z]\d{5,}', nombre):
                nombres.setdefault(codigo, nombre.title())
        if 'cancel' in str(d.get('Task Status') or '').lower():
            continue
        tipo = _tipo(d, clave)
        if not tipo:
            continue
        inicio = str((d.get('Dispatch Time') if tipo == 'CM' else d.get('Arrive Time')) or '').strip()
        estado_ticket = str(d.get('Task Status') or '').strip().lower()
        salida.append({
            'ticket': str(d.get('Ticket Id') or clave), 'tipo': tipo, 'site': str(d.get('Site Name') or ''),
            'tecnico': str(d.get('Schedule Operator') or '').strip(), 'estado_ticket': str(d.get('Task Status') or ''),
            'inicio': inicio[:19], 'fin': str(d.get('Complete Time') or (d.get('FECHA CAMBIO ESTADO') if estado_ticket in ('completed', 'closed') else '') or '').strip()[:19],
            # Cerrado = el ticket ya está completed (o closed); ahí se usa SLA Status y SLA Hour.
            'cerrado': estado_ticket in ('completed', 'closed'),
            # Columnas reales, para verlas tal cual en la tabla.
            'dispatch': str(d.get('Dispatch Time') or '').strip()[:19], 'arrive': str(d.get('Arrive Time') or '').strip()[:19],
            'sla_hour': str(d.get('SLA Hour') or '').strip(), 'categoria': str(d.get('Task Category') or '').strip(), 'sla_status_original': str(d.get('SLA Status') or '').strip(),
            'objetivo': _minutos(d.get('SLA Hour')), 'sla_status': str(d.get('SLA Status') or '').strip().lower(),
            'prioridad': str(d.get('Fault Level label') or d.get('Fault Level') or ''),
        })
    for c in salida:
        c['tecnico_nombre'] = nombres.get(c['tecnico'], '')
    return salida


@bp.get('/sla/')
@login_required
def pagina():
    permitidos = _permitidos()
    if not permitidos:
        abort(403)
    return render_template('sla.html', proyectos=permitidos, con_criterios=sorted(CON_CRITERIOS),
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')),
                           por_vencer={'porcentaje': POR_VENCER_PORCENTAJE, 'minutos': POR_VENCER_MINUTOS})


@bp.get('/api/sla/<familia>')
@login_required
def datos(familia):
    proyecto = next((p for p in _permitidos() if p[0] == familia.upper()), None)
    if not proyecto:
        abort(404)
    if proyecto[0] not in CON_CRITERIOS:
        return jsonify(casos=[], pendiente=True)
    modulo = Proyecto.query.filter_by(nombre=proyecto[1]).first()
    if not modulo:
        return jsonify(casos=[])
    return jsonify(casos=casos(modulo))


# ── Alertas: casos por vencer, para avisar en todas las pantallas ──
_CACHE_ALERTAS = {}


def por_vencer(modulo, ahora=None):
    """Casos abiertos con poco tiempo (≤ 25 % del objetivo o ≤ 60 min), del más urgente al menos urgente."""
    from datetime import datetime, timedelta
    ahora = ahora or (datetime.utcnow() - timedelta(hours=5))  # hora de Perú, como vienen las fechas
    salida = []
    for c in casos(modulo):
        if c['cerrado'] or not c['objetivo'] or not c['inicio']:
            continue
        try:
            inicio = datetime.strptime(c['inicio'][:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        resto = c['objetivo'] - ((ahora - inicio).total_seconds() / 60 - c.get('pausa', 0))
        if 0 <= resto and (resto <= c['objetivo'] * POR_VENCER_PORCENTAJE or resto <= POR_VENCER_MINUTOS):
            salida.append({'ticket': c['ticket'], 'tipo': c['tipo'], 'site': c['site'], 'categoria': c.get('categoria', ''),
                           'tecnico': c['tecnico'], 'tecnico_nombre': c['tecnico_nombre'], 'resto': round(resto)})
    return sorted(salida, key=lambda x: x['resto'])


@bp.get('/api/sla/alertas')
@login_required
def alertas():
    """Casos por vencer de los proyectos FLM (con criterios) que el usuario puede ver. Se recalcula cada minuto."""
    import time
    resultado = []
    for clave, nombre_modulo, nombre, _color in _permitidos():
        if clave not in CON_CRITERIOS:
            continue
        guardado = _CACHE_ALERTAS.get(clave)
        if not guardado or time.time() - guardado[0] > 60:
            modulo = Proyecto.query.filter_by(nombre=nombre_modulo).first()
            guardado = (time.time(), por_vencer(modulo) if modulo else [])
            _CACHE_ALERTAS[clave] = guardado
        resultado += [{**c, 'proyecto': nombre} for c in guardado[1]]
    return jsonify(alertas=sorted(resultado, key=lambda x: x['resto']))
