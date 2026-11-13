"""Mobile · restricciones para que los técnicos rindan antes de pedir más Caja Chica.

Cada regla se activa o desactiva, tiene su valor (monto, horas o cantidad) y los proyectos
a los que aplica. Se guarda en AppConfig del módulo Caja Chica (clave CLAVE)."""
import json
from datetime import datetime, timedelta
from decimal import Decimal

from db import db
from models import AppConfig, CajaChicaSolicitud, Proyecto
from services import caja_chica as cc

CLAVE = 'mobile_reglas'
PROYECTOS = ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT')
# nombre: (texto, unidad, valor por defecto)
REGLAS = {
    'aviso': ('Aviso si el monto por rendir pasa de', 'S/', 500),
    'tope': ('No deja solicitar si el monto por rendir pasa de', 'S/', 600),
    'plazo': ('No deja solicitar si tiene un depósito sin rendir de más de', 'horas', 48),
    'refacturables': ('Máximo de solicitudes refacturables sin rendir', 'solicitudes', 2),
}
ACTIVAS = ('PENDIENTE', 'RECHAZADO', 'VALIDADO', 'DEPOSITADO', 'POR_DEVOLVER')
# Tipo de gasto que cuenta cada regla (la de refacturables siempre es Refacturable).
GASTOS = {'ambos': 'Gasto Cobra y Refacturable', 'cobra': 'Solo Gasto Cobra', 'refacturable': 'Solo Refacturable'}
CON_GASTO = ('aviso', 'tope', 'plazo')


def _modulo_id():
    return Proyecto.query.filter_by(nombre=cc.MODULO).with_entities(Proyecto.id).scalar()


def leer():
    """Reglas guardadas, completadas con los valores por defecto (todas activas, en todos los proyectos)."""
    guardadas = {}
    fila = AppConfig.query.filter_by(proyecto_id=_modulo_id(), clave=CLAVE).first()
    if fila:
        try:
            guardadas = json.loads(fila.valor) or {}
        except ValueError:
            guardadas = {}
    reglas = {}
    for nombre, (_, _, defecto) in REGLAS.items():
        r = guardadas.get(nombre) if isinstance(guardadas.get(nombre), dict) else {}
        try:
            valor = Decimal(str(r.get('valor', defecto)))
        except ArithmeticError:
            valor = Decimal(defecto)
        proyectos = r.get('proyectos', list(PROYECTOS))
        reglas[nombre] = {'activa': bool(r.get('activa', True)), 'valor': valor,
                          'proyectos': [p for p in PROYECTOS if p in (proyectos or [])],
                          'gasto': r.get('gasto') if r.get('gasto') in GASTOS and nombre in CON_GASTO else 'ambos'}
    return reglas


def guardar(datos, usuario):
    """datos: {regla: {activa, valor, proyectos}} (del formulario de Mobile)."""
    limpio = {}
    for nombre, (texto, _, _) in REGLAS.items():
        r = datos.get(nombre) or {}
        try:
            valor = Decimal(str(r.get('valor', '')).replace(',', '.').strip())
        except ArithmeticError:
            raise ValueError('%s: escribe un número válido.' % texto) from None
        if valor <= 0 or (nombre in ('plazo', 'refacturables') and valor != valor.to_integral()):
            raise ValueError('%s: escribe un número mayor a cero%s.' % (texto, '' if nombre in ('aviso', 'tope') else ' y sin decimales'))
        gasto = r.get('gasto') or 'ambos'
        if gasto not in GASTOS:
            raise ValueError('%s: elige Gasto Cobra, Refacturable o ambos.' % texto)
        limpio[nombre] = {'activa': bool(r.get('activa')), 'valor': str(valor),
                          'proyectos': [p for p in PROYECTOS if p in (r.get('proyectos') or [])],
                          'gasto': gasto if nombre in CON_GASTO else 'ambos'}
    if limpio['aviso']['activa'] and limpio['tope']['activa'] and Decimal(limpio['aviso']['valor']) >= Decimal(limpio['tope']['valor']):
        raise ValueError('El aviso debe ser menor que el tope para solicitar.')
    pid = _modulo_id()
    fila = AppConfig.query.filter_by(proyecto_id=pid, clave=CLAVE).first()
    if not fila:
        fila = AppConfig(proyecto_id=pid, clave=CLAVE, valor='{}')
        db.session.add(fila)
    limpio['_editado'] = {'usuario': usuario, 'fecha': datetime.utcnow().isoformat(timespec='seconds')}
    fila.valor = json.dumps(limpio, ensure_ascii=False)
    db.session.commit()


def _refacturable(texto):
    return 'refact' in str(texto or '').lower()


def _tipos(sol):
    """{numero de ítem: 'refacturable' | 'cobra'} según los conceptos de la solicitud."""
    historial = json.loads(sol.historial or '[]')
    conceptos = next((e['conceptos'] for e in reversed(historial) if 'conceptos' in e), {})
    return {item.numero: 'refacturable' if _refacturable((conceptos.get(str(item.numero)) or {}).get('tipo_presupuesto')) else 'cobra'
            for item in sol.items}


def _por_rendir(sol, gasto):
    """Lo que el técnico aún debe rendir o devolver de esta solicitud, solo del tipo de gasto pedido."""
    if sol.estado not in ('DEPOSITADO', 'POR_DEVOLVER'):
        return Decimal('0')
    if gasto == 'ambos':
        return cc.montos_etapa(sol).get('por_rendir', Decimal('0'))
    tipos, total = _tipos(sol), Decimal('0')
    for item in sol.items:
        if tipos.get(item.numero) != gasto:
            continue
        if item.estado in ('POR_RENDIR', 'RECHAZADO'):
            total += item.monto
        elif sol.estado == 'POR_DEVOLVER' and not sol.devolucion_foto:
            # Saldo que va a la devolución: lo no gastado del ítem (todo, si se devolvió completo).
            total += item.monto if item.estado == 'DEVUELTO' else max(Decimal('0'), item.monto - (item.monto_gastado or Decimal('0')))
    return total


def _de_tipo(gasto):
    return '' if gasto == 'ambos' else (' de Gasto Cobra' if gasto == 'cobra' else ' Refacturable')


def _refacturable_pendiente(sol):
    """La solicitud tiene un concepto refacturable que el técnico aún no rinde."""
    historial = json.loads(sol.historial or '[]')
    conceptos = next((e['conceptos'] for e in reversed(historial) if 'conceptos' in e), {})
    for item in sol.items:
        if not _refacturable((conceptos.get(str(item.numero)) or {}).get('tipo_presupuesto')):
            continue
        if sol.estado in ('PENDIENTE', 'RECHAZADO', 'VALIDADO') or item.estado in ('POR_RENDIR', 'RECHAZADO'):
            return True
    return False


def estado(documento, proyecto, ahora=None):
    """Situación del técnico frente a las reglas que aplican a su proyecto.

    Devuelve por_rendir, aviso (texto o ''), bloqueos (textos que impiden solicitar)
    y el conteo de refacturables pendientes."""
    reglas = leer()
    ahora = ahora or datetime.utcnow()
    aplica = {n: r for n, r in reglas.items() if r['activa'] and proyecto in r['proyectos']}
    solicitudes = (CajaChicaSolicitud.query.filter_by(documento=documento)
                   .filter(CajaChicaSolicitud.estado.in_(ACTIVAS)).all())

    def en(nombre):
        return [s for s in solicitudes if s.proyecto in reglas[nombre]['proyectos']]

    def por_rendir(lista, gasto='ambos'):
        return sum((_por_rendir(s, gasto) for s in lista), Decimal('0'))

    # bloqueos: impiden cualquier solicitud ('ambos'); bloqueos_tipo: solo impiden pedir ese tipo de gasto.
    resultado = {'por_rendir': cc.dinero(por_rendir(solicitudes)), 'aviso': '', 'bloqueos': [], 'bloqueos_tipo': [],
                 'tope': '', 'tope_gasto': 'ambos', 'refacturables': None}

    def bloquear(gasto, texto):
        if gasto == 'ambos':
            resultado['bloqueos'].append(texto)
        else:
            resultado['bloqueos_tipo'].append({'gasto': gasto, 'mensaje': texto})

    if 'tope' in aplica:
        gasto = aplica['tope']['gasto']
        monto, tope = por_rendir(en('tope'), gasto), aplica['tope']['valor']
        resultado.update(tope=cc.dinero(tope), tope_gasto=gasto, por_rendir_tope=cc.dinero(monto))
        if monto > tope:
            bloquear(gasto, 'Tienes S/ %s por rendir%s y el tope es S/ %s. Rinde tus pendientes para volver a solicitar%s.'
                     % (cc.dinero(monto), _de_tipo(gasto), cc.dinero(tope), _de_tipo(gasto)))
    if 'aviso' in aplica and not resultado['bloqueos']:
        gasto = aplica['aviso']['gasto']
        monto = por_rendir(en('aviso'), gasto)
        if monto > aplica['aviso']['valor']:
            tope = ' Si pasas de S/ %s no podrás solicitar.' % resultado['tope'] if resultado['tope'] else ''
            resultado['aviso'] = 'Tienes S/ %s por rendir%s. Rinde tus pendientes.%s' % (cc.dinero(monto), _de_tipo(gasto), tope)
    if 'plazo' in aplica:
        gasto = aplica['plazo']['gasto']
        horas = int(aplica['plazo']['valor'])
        limite = ahora - timedelta(hours=horas)
        vencidas = [s.codigo for s in en('plazo') if s.estado in ('DEPOSITADO', 'POR_DEVOLVER') and s.depositado_en
                    and s.depositado_en < limite and _por_rendir(s, gasto) > 0]
        if vencidas:
            bloquear(gasto, 'Tienes depósitos%s con más de %d h sin rendir (%s). Ríndelos para volver a solicitar%s.'
                     % (_de_tipo(gasto), horas, ', '.join(vencidas), _de_tipo(gasto)))
    if 'refacturables' in aplica:
        maximo = int(aplica['refacturables']['valor'])
        pendientes = sum(_refacturable_pendiente(s) for s in en('refacturables'))
        resultado['refacturables'] = {'pendientes': pendientes, 'maximo': maximo}
    return resultado


def exigir_para_solicitar(documento, proyecto, conceptos):
    """Se llama antes de crear una solicitud nueva (no al corregir una rechazada)."""
    situacion = estado(documento, proyecto)
    if situacion['bloqueos']:
        raise ValueError(situacion['bloqueos'][0])
    pide = {'refacturable' if _refacturable(c.get('tipo_presupuesto')) else 'cobra' for c in conceptos.values()}
    for bloqueo in situacion['bloqueos_tipo']:
        if bloqueo['gasto'] in pide:
            raise ValueError(bloqueo['mensaje'])
    refact = situacion['refacturables']
    if refact and refact['pendientes'] >= refact['maximo'] \
            and any(_refacturable(c.get('tipo_presupuesto')) for c in conceptos.values()):
        raise ValueError('Ya tienes %d solicitudes con conceptos refacturables sin rendir (máximo %d). '
                         'Rinde una para pedir otro refacturable.' % (refact['pendientes'], refact['maximo']))
