"""SLA: cumplimiento de los tickets FLM (CM, PM y PLM) por proyecto.

Reglas:
- CM: cuenta desde Dispatch Time; PM y PLM: desde Arrive Time. Termina en Complete Time.
- Objetivo: SLA Hour (minutos). Resultado de un cerrado: SLA Status ("normal" cumple; "sla_violation" no).
- Abiertos: vencido, por vencer (queda ≤ 25 % del objetivo o ≤ 60 min) o en plazo.
- Técnico: Schedule Operator.
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
CON_CRITERIOS = {'CLARO'}
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


def casos(proyecto):
    """Casos del proyecto con lo necesario para el SLA (sin cancelados)."""
    filas = (NucleusData.query.filter_by(proyecto_id=proyecto.id)
             .with_entities(NucleusData.key_value, NucleusData.data_json))
    nombres, salida = {}, []
    for clave, crudo in filas:
        try:
            d = json.loads(crudo or '{}')
        except ValueError:
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
        salida.append({
            'ticket': str(d.get('Ticket Id') or clave), 'tipo': tipo, 'site': str(d.get('Site Name') or ''),
            'tecnico': str(d.get('Schedule Operator') or '').strip(), 'estado_ticket': str(d.get('Task Status') or ''),
            'inicio': inicio[:19], 'fin': str(d.get('Complete Time') or '').strip()[:19],
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
        if c['fin'] or not c['objetivo'] or not c['inicio']:
            continue
        try:
            inicio = datetime.strptime(c['inicio'][:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        resto = c['objetivo'] - (ahora - inicio).total_seconds() / 60
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
