"""Resumen ejecutivo de solo lectura, limitado al alcance de la sesión."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from models import AccesoProyecto, NucleusData, RefacturableDetalle
from services import dashboard_claro, dashboard_integratel
from services.combustible import _parse_galones
from services.dashboard_consulta import dia, gasto, valor
from services.dashboard_cotizaciones import _en_proveedor, _money, _pestania
from services.recursos_flm import familia
from services.rendicion_estados import etapa_de, estado_de
from services.utilidades import apply_data_restrictions


OPERADORES = {'ENTEL': 'entel', 'CLARO': 'claro', 'INTEGRATEL': 'integratel', 'PEXT': 'pext'}
CATALOGOS = {'Dataper': 'Personal', 'Material': 'Material', 'SITE': 'Sites',
             'Generadores': 'Generadores', 'Combustible': 'Combustible'}


def _objeto(text):
    try:
        data = json.loads(text or '{}')
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _operacion(rows, operador, hoy):
    if operador == 'CLARO':
        data = dashboard_claro.indicadores(rows)['rows']
        ordenes = [
            (dia(r['creacion']), dia(r['cierre']), r['completado'], r['sla'])
            for r in data if not r['cancelado']
        ]
    else:
        data = dashboard_integratel.indicadores(rows, hoy, integratel=operador == 'INTEGRATEL')['detalle']
        ordenes = [
            (r['fecha'], dia(r['cierre']), r['grupo'] == 'Producción', r['sla'])
            for r in data if not r['cancelado']
        ]
    mes = hoy.strftime('%Y-%m')
    fecha_corte = hoy.isoformat()
    limite = (hoy - timedelta(days=7)).isoformat()
    medidas = [sla for _, _, cerrada, sla in ordenes if cerrada and sla is not None]
    return {
        'nombre': operador.title() if operador != 'PEXT' else operador,
        'url': '/analytics/' + OPERADORES[operador],
        'total': len(ordenes),
        'creadas': sum(creacion.startswith(mes) and creacion <= fecha_corte for creacion, _, _, _ in ordenes),
        'cierres': sum(cerrada and cierre.startswith(mes) and cierre <= fecha_corte for _, cierre, cerrada, _ in ordenes),
        'abiertas': sum(not cerrada for _, _, cerrada, _ in ordenes),
        'antiguas': sum(not cerrada and bool(creacion) and creacion <= limite for creacion, _, cerrada, _ in ordenes),
        'sin_fecha': sum(not creacion for creacion, _, _, _ in ordenes),
        'sin_cierre': sum(cerrada and not cierre for _, cierre, cerrada, _ in ordenes),
        'sla_base': len(medidas), 'sla_fuera': medidas.count(False),
        'sla': 100 * medidas.count(True) / len(medidas) if medidas else None,
    }


def resumen(proyectos, usuario, rol, ahora=None):
    from blueprints.refacturable import _aprobada, _ingresada

    ahora = ahora or datetime.now(ZoneInfo('America/Lima'))
    hoy = ahora.date()
    global_ = rol == 'zeno'
    accesos = {} if global_ else {
        acceso.proyecto_id: _objeto(acceso.restricciones)
        for acceso in AccesoProyecto.query.filter_by(usuario_id=usuario)
    }
    por_nombre = {p.nombre: p for p in proyectos}
    flm = {op: por_nombre.get('FLM - ' + op) or (por_nombre.get('PEXT') if op == 'PEXT' else None)
           for op in OPERADORES}
    familias = {op for op, p in flm.items() if p and (global_ or accesos.get(p.id) is not None)}
    familias_catalogo = {op for op in familias if not accesos.get(flm[op].id)}
    alertas = defaultdict(lambda: {'cantidad': 0, 'monto': 0.0})
    operaciones, modulos = [], []
    finanzas = defaultdict(Counter)
    depositos = {tipo: Counter() for tipo in ('Gasto Cobra', 'Refacturable', 'Sin clasificar')}
    depositos_por_fecha = defaultdict(Counter)
    gastos_cobra, refacturables_caja, refacturables_proveedor = [], [], []

    def filas(p, *, compartido=False, liquidaciones=False):
        restricciones = {} if global_ else accesos.get(p.id)
        inferido = restricciones is None and p.id not in accesos and compartido and bool(familias_catalogo)
        if restricciones is None and not inferido:
            return
        query = NucleusData.query.filter_by(proyecto_id=p.id)
        if liquidaciones:
            query = query.outerjoin(RefacturableDetalle, RefacturableDetalle.origen_id == NucleusData.id)
            query = query.with_entities(NucleusData.key_value, NucleusData.data_json, RefacturableDetalle.data_json)
        else:
            query = query.with_entities(NucleusData.key_value, NucleusData.data_json)
        for registro in query.yield_per(500):
            key, text = registro[:2]
            row = _objeto(text)
            if row is None:
                continue
            if inferido and familia(valor(row, 'PROYECTO')) not in familias_catalogo:
                continue
            if restricciones and (any(col not in row for col, permitidos in restricciones.items() if permitidos)
                                  or not apply_data_restrictions([row], restricciones)):
                continue
            row['_key'] = key
            yield (row, _objeto(registro[2]) or {}) if liquidaciones else row

    def alerta(titulo, grupo, url, cantidad=1, monto=0, *, nivel='atención', monetaria=False):
        if cantidad:
            entry = alertas[titulo, grupo, url, nivel, monetaria]
            entry['cantidad'] += cantidad
            entry['monto'] += monto

    for op in OPERADORES:
        if op not in familias:
            continue
        item = _operacion(filas(flm[op]), op, hoy)
        operaciones.append(item)
        alerta('Órdenes abiertas desde hace 7 días o más', item['nombre'], item['url'], item['antiguas'])
        alerta('Cierres fuera de SLA', item['nombre'], item['url'], item['sla_fuera'], nivel='prioritaria')
        alerta('Órdenes sin fecha de creación', item['nombre'], item['url'], item['sin_fecha'], nivel='calidad')

    cot = por_nombre.get('Cotizaciones')
    ve_cot = bool(cot and (global_ or accesos.get(cot.id) is not None))
    if ve_cot:
        estados = Counter()
        montos = Counter()
        liquidaciones = Counter()
        for row, seguimiento in filas(cot, liquidaciones=True):
            etapa = _pestania(row)
            monto = _money(row.get('SUB TOTAL + FEE'))
            grupo = familia(valor(row, 'CLIENTE', 'PROYECTO')) or 'Sin proyecto identificado'
            if gasto(valor(row, 'TIPO DE GASTO', 'TIPO DE PRESUPUESTO'), '') == 'Refacturable' and _en_proveedor(row):
                refacturables_proveedor.append({
                    'codigo': valor(row, 'N° COTIZACION') or row['_key'],
                    'proyecto': grupo, 'monto': _money(row.get('SUBTOTAL FACTURA PROVEEDOR')),
                    'estado': row.get('ESTADO COTIZACION') or '',
                })
            estados[etapa] += 1
            montos[etapa] += monto
            if etapa == 'cliente':
                finanzas[grupo]['en_aprobacion'] += monto
                alerta('Cotizaciones pendientes de aprobación', grupo, '/analytics/cotizaciones', monto=monto, monetaria=True)
            elif etapa == 'sustentar':
                alerta('Cotizaciones aprobadas pendientes de atención', grupo, '/analytics/cotizaciones', monto=monto, monetaria=True)
            if _ingresada(row):
                estado = seguimiento.get('estado_liquidacion') or seguimiento.get('estado_expense') or 'Pendiente'
                liquidaciones[estado] += 1
                aprobada = _aprobada(row) and etapa != 'cliente'
                importe = _money(seguimiento.get('monto_cobra')) if aprobada else 0
                if estado in ('Observado', 'Rechazado'):
                    alerta('Liquidaciones observadas o rechazadas', grupo, '/liquidaciones/',
                           monto=max(0, importe), nivel='prioritaria', monetaria=True)
                if aprobada:
                    if importe > 0:
                        finanzas[grupo]['por_cobrar_registrado'] += importe
                    else:
                        finanzas[grupo]['estimado'] += max(0, monto)
                        alerta('Confirmar monto de cotizaciones aprobadas', grupo, '/liquidaciones/',
                               monto=max(0, monto), nivel='calidad', monetaria=True)
        modulos.extend([
            ('Cotizaciones', '/analytics/cotizaciones', [
                ('Registros', estados.total(), False), ('En aprobación', estados['cliente'], False),
                ('Importe en aprobación', montos['cliente'], True), ('Aprobadas por atender', estados['sustentar'], False),
            ]),
            ('Liquidaciones', '/liquidaciones/', [
                ('Casos', liquidaciones.total(), False), ('Pendientes', liquidaciones['Pendiente'], False),
                ('En revisión', liquidaciones['En revisión'], False), ('Con PO', liquidaciones['Con PO'], False),
            ]),
        ])

    rend = por_nombre.get('Rendicion')
    ve_rend = bool(rend and (global_ or accesos.get(rend.id) is not None))
    if ve_rend:
        etapas = Counter()
        pendiente = 0
        corte = ahora.replace(tzinfo=None) - timedelta(hours=24)
        for row in filas(rend):
            etapa = etapa_de(row)
            etapas[etapa] += 1
            grupo = familia(valor(row, 'Nombre del proyecto', 'PROYECTO', 'CLIENTE')) or 'Sin proyecto identificado'
            pagado = _money(row.get('MONTO PAGO'))
            if pagado > 0 and etapa in ('EVIDENCIA', 'SUSTENTO', 'OBSERVADO', 'ATENDIDO', 'ARCHIVADO'):
                tipo = gasto(valor(row, 'Tipo de presupuesto'), 'Sin clasificar')
                if tipo not in depositos:
                    tipo = 'Sin clasificar'
                resumen_deposito = depositos[tipo]
                resumen_deposito['depositado'] += pagado
                resumen_deposito['casos'] += 1
                fecha_pago = dia(row.get('FECHA PAGO'))
                if fecha_pago:
                    depositos_por_fecha[fecha_pago][tipo] += pagado
                por_rendir = etapa in ('EVIDENCIA', 'OBSERVADO')
                if por_rendir:
                    resumen_deposito['por_rendir'] += pagado
                    resumen_deposito['casos_por_rendir'] += 1
                if etapa == 'SUSTENTO':
                    resumen_deposito['por_validar'] += pagado
                if tipo in ('Gasto Cobra', 'Refacturable'):
                    detalle_pago = gastos_cobra if tipo == 'Gasto Cobra' else refacturables_caja
                    detalle_pago.append({
                        'codigo': valor(row, 'CODIGO DEPOSITO') or row['_key'],
                        'cotizacion': valor(row, 'N° COTIZACION'),
                        'proyecto': grupo, 'monto': pagado, 'estado': etapa,
                        'fecha': fecha_pago,
                    })
            if etapa == 'DEPOSITOS':
                finanzas[grupo]['por_depositar'] += _money(row.get('Monto total del depósito'))
            if estado_de(row) == 'DEPOSITADO':
                pendiente += pagado
                finanzas[grupo]['sin_sustento'] += pagado
                pago = row.get('FECHA PAGO')
                fecha_pago = dashboard_integratel.instante(pago)
                if fecha_pago:
                    momento = datetime.fromisoformat(fecha_pago)
                    if ':' not in str(pago):
                        momento = momento.replace(hour=23, minute=59, second=59)
                    if momento < corte:
                        finanzas[grupo]['sin_sustento_vencido'] += pagado
                        alerta('Depósitos con más de 24 h sin sustento', grupo, '/analytics/rendicion',
                               monto=pagado, nivel='prioritaria', monetaria=True)
                else:
                    alerta('Depósitos sin fecha de pago', grupo, '/analytics/rendicion', nivel='calidad')
            if etapa == 'OBSERVADO':
                alerta('Rendiciones observadas', grupo, '/analytics/rendicion', monto=pagado, monetaria=True)
        modulos.append(('Caja Chica', '/analytics/rendicion', [
            ('Registros', etapas.total(), False), ('Por depositar', etapas['DEPOSITOS'], False),
            ('En evidencia', etapas['EVIDENCIA'], False), ('Depositado sin sustento', pendiente, True),
            ('Observadas', etapas['OBSERVADO'], False),
        ]))

    for nombre, etiqueta in CATALOGOS.items():
        p = por_nombre.get(nombre)
        compartido = nombre in ('Dataper', 'Material')
        if not p or not (global_ or accesos.get(p.id) is not None or
                         (compartido and p.id not in accesos and familias_catalogo)):
            continue
        conteos = Counter()
        saldos = Counter()
        url = f'/switch_project/{p.id}?next=/'
        for row in filas(p, compartido=compartido):
            conteos['Registros'] += 1
            if nombre == 'Dataper' and str(valor(row, 'ESTADO')).strip().upper() == 'ACTIVO':
                conteos['Activos'] += 1
                if not valor(row, 'SUPERVISOR'):
                    conteos['Activos sin supervisor'] += 1
                    grupo = familia(valor(row, 'PROYECTO')) or etiqueta
                    alerta('Personal activo sin supervisor', grupo, url, nivel='calidad')
            elif nombre == 'Material' and not valor(row, 'PROYECTO'):
                conteos['Sin proyecto'] += 1
            elif nombre == 'SITE' and not all([valor(row, 'Latitud', 'Latitud (°)'), valor(row, 'Longitud', 'Longitud (°)')]):
                conteos['Sin coordenadas'] += 1
            elif nombre == 'Combustible':
                qr = str(valor(row, 'QR ASIGNADO')).strip()
                movimiento = str(valor(row, 'MOVIMIENTO')).strip().upper()
                if qr and movimiento in ('INGRESO', 'GASTO'):
                    galones = _parse_galones(valor(row, 'GALONES'))
                    saldos[qr] += galones if movimiento == 'INGRESO' else -galones
        if nombre == 'Combustible':
            conteos['QR con saldo negativo'] = sum(saldo < -1e-9 for saldo in saldos.values())
            alerta('Generadores con saldo de combustible negativo', etiqueta, url,
                   conteos['QR con saldo negativo'], nivel='prioritaria')
        extras = {'Dataper': ('Activos', 'Activos sin supervisor'), 'Material': ('Sin proyecto',),
                  'SITE': ('Sin coordenadas',), 'Combustible': ('QR con saldo negativo',)}.get(nombre, ())
        modulos.append((etiqueta, url, [(k, conteos[k], False) for k in ('Registros', *extras)]))

    niveles = {'prioritaria': 0, 'atención': 1, 'calidad': 2}
    filas_alerta = [
        dict(titulo=titulo, grupo=grupo, url=url, nivel=nivel, monetaria=monetaria, **info)
        for (titulo, grupo, url, nivel, monetaria), info in alertas.items()
    ]
    filas_alerta.sort(key=lambda r: (niveles[r['nivel']], -r['cantidad'], r['titulo'], r['grupo']))
    totales = Counter()
    for montos in finanzas.values():
        totales.update(montos)
    impactos = sorted(
        (a for a in filas_alerta if a['monetaria'] and a['monto'] > 0),
        key=lambda a: (-a['monto'], niveles[a['nivel']], a['grupo'], a['titulo']),
    )
    proyectos_finanzas = sorted(finanzas.items(), key=lambda item: (
        -item[1]['por_cobrar_registrado'], -item[1]['en_aprobacion'], -item[1]['sin_sustento'], item[0],
    ))
    totales_depositos = Counter()
    for montos in depositos.values():
        totales_depositos.update(montos)
    return {'hoy': hoy.isoformat(), 'mes': hoy.strftime('%Y-%m'), 'operaciones': operaciones,
            'depositos': depositos, 'totales_depositos': totales_depositos,
            'depositos_por_fecha': dict(sorted(depositos_por_fecha.items())),
            'gastos_cobra': sorted(gastos_cobra, key=lambda row: (row['fecha'], row['codigo']), reverse=True),
            'refacturables_caja': sorted(refacturables_caja, key=lambda row: (row['fecha'], row['codigo']), reverse=True),
            'refacturables_proveedor': sorted(refacturables_proveedor, key=lambda row: (-row['monto'], row['codigo'])),
            'modulos': modulos, 'alertas': filas_alerta, 'impactos': impactos, 'finanzas': dict(proyectos_finanzas),
            'totales_finanzas': totales, 've_cot': ve_cot, 've_rend': ve_rend}
