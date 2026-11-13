"""Revisión (solo lectura) de la migración Cotizaciones old → Cotizaciones (vista nueva).

No cambia nada en la base: arma un Excel con cada cotización, dónde está hoy en el módulo
old, dónde caerá en la vista nueva, sus estados de pago y operativo, y qué habría que
completar para que cuadre (por ejemplo, los Tránsitos del flujo anterior que viven en Rendición).

Uso:
  python scripts/revision_migracion_cotizaciones.py cotizaciones.json rendicion.json salida.xlsx
     (JSON: lista de {"id", "key_value", "data_json"} de cada módulo)
  python scripts/revision_migracion_cotizaciones.py --db salida.xlsx
     (lee la base configurada en DATABASE_URL)
"""
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PESTANA_OLD = {
    'atendido': 'Atendido', 'validado': 'Atendido', 'cotizado': 'Cliente', 'en aprobación': 'Cliente',
    'en aprobacion': 'Cliente', 'sustentar': 'Sustentar', 'aprobado': 'Sustentar',
    'cancelado': 'Anulado', 'anulado': 'Anulado', 'anulada': 'Anulado',
}
NOMBRE_NUEVA = {'registro': 'Registro', 'cliente': 'Cliente', 'cajachica': 'Caja chica', 'transito': 'Tránsito',
                'proveedor': 'Proveedor', 'sustentar': 'Operaciones', 'atendido': 'Atendido', 'cancelado': 'Anulado',
                'pendientes': 'WO / Site pendiente'}


def _num(valor):
    try:
        return Decimal(str(valor or '').replace(',', '').replace('S/', '').strip() or '0')
    except InvalidOperation:
        return Decimal('0')


def _transitos_old(rendicion):
    """Cotizaciones enviadas a Tránsito con el flujo anterior (viven en Rendición)."""
    resultado = {}
    for fila in rendicion:
        datos = json.loads(fila['data_json'] or '{}') if isinstance(fila['data_json'], str) else (fila['data_json'] or {})
        origen = datos.get('_COTIZACION_ORIGEN') or {}
        if origen.get('key'):
            resultado[origen['key']] = {'clave_rendicion': fila['key_value'], 'estado': str(datos.get('ESTADO') or '').strip().upper(),
                                        'monto': datos.get('Monto total del depósito', ''),
                                        'fecha': datos.get('FECHA ENVIO TRANSITO', ''), 'usuario': datos.get('ENVIADO A TRANSITO POR', '')}
    return resultado


def analizar(cotizaciones, rendicion):
    from blueprints import cot_new as nuevo
    from services.rendicion_presupuesto_cotizacion import monto_cotizacion, proyecto as familia
    transitos = _transitos_old(rendicion)
    filas = []
    for fila in cotizaciones:
        datos = json.loads(fila['data_json'] or '{}') if isinstance(fila['data_json'], str) else (fila['data_json'] or {})
        key = fila['key_value']
        estado = str(datos.get('ESTADO COTIZACION') or '').strip()
        old = PESTANA_OLD.get(estado.lower(), 'Registro')
        tipo = nuevo.tipo_atencion(datos)
        cambios, alertas = {}, []
        transito = transitos.get(key)
        # Bandejas extra del módulo old.
        extra_old = []
        if transito and transito['estado'] == 'TRANSITO':
            extra_old.append('Tránsito')
        if str(datos.get('TIPO GASTO APROBACION') or '').strip().casefold() == 'proveedor' and old in ('Sustentar', 'Atendido'):
            extra_old.append('Proveedor')

        if estado and estado.lower() not in PESTANA_OLD and estado.lower() not in ('pdt. cotización', 'pdt. cotizacion'):
            alertas.append('Estado "%s" no reconocido: en la vista nueva cae en Registro.' % estado)
        aprobada = nuevo.aprobada(datos)
        if aprobada and not tipo and not transito:
            alertas.append('Aprobada sin "Se atiende con" (Caja chica / Proveedor / Tránsito): se verá como Depositado Caja Chica.')
        if transito and tipo != 'Tránsito':
            # Tránsito del flujo anterior: se marca como Tránsito pagado para que aparezca en su pestaña.
            cambios['TIPO GASTO APROBACION'] = 'Tránsito'
            cambios['MONTO TRANSITO'] = '%.2f' % (_num(transito['monto']) or _num(datos.get('SUB TOTAL + FEE')))
            if not datos.get('FECHA PAGO'):
                cambios['FECHA PAGO'] = transito['fecha']
                cambios['PAGADO POR'] = transito['usuario']
                cambios['MONTO PAGADO'] = cambios['MONTO TRANSITO']
            if transito['estado'] != 'TRANSITO':
                cambios['_TRANSITO_A_PROVEEDOR'] = '1'
            alertas.append('Tránsito del flujo anterior (Rendición %s, %s): confirmar monto y fecha de depósito.'
                           % (transito['clave_rendicion'], transito['estado'] or 'sin estado'))
        monto = _num(monto_cotizacion(datos.get('SUB TOTAL + FEE'), datos.get('ITEMS_JSON')))
        if monto <= 0 and old not in ('Anulado', 'Registro'):
            alertas.append('Sin monto (Sub total + FEE en 0).')

        propuesto = {**datos, **cambios}
        nuevas = [NOMBRE_NUEVA[p] for p in nuevo.pestanas_de(propuesto)]
        principal_nueva = NOMBRE_NUEVA[nuevo.pestana_de(propuesto)]
        principal_old = old
        mismo = (principal_old == principal_nueva) or (principal_old == 'Sustentar' and principal_nueva == 'Operaciones')
        if not mismo:
            alertas.append('Cambia de pestaña: %s → %s.' % (principal_old, principal_nueva))
        filas.append({
            'N° COTIZACION': datos.get('N° COTIZACION') or key, 'Clave': key, 'Cliente': familia(datos) or datos.get('CLIENTE') or '',
            'Fecha': datos.get('FECHA', ''), 'Site': datos.get('NOMBRE SITE', ''), 'N.º WO': datos.get('NUMERO WO', ''),
            'Motivo / objetivo': datos.get('OBJETIVO') or datos.get('MOTIVO') or '', 'Sub total + FEE': float(monto),
            'Estado guardado': estado or '(vacío)',
            'Pestaña old': ' + '.join([principal_old] + extra_old),
            'Pestaña(s) nueva(s)': ' + '.join(nuevas),
            'Se atiende con (hoy)': tipo or '—', 'Se atiende con (migrado)': nuevo.tipo_atencion(propuesto) or '—',
            'Falta WO / site': 'Sí' if nuevo.falta_wo_site(propuesto) else 'No',
            'Estado de pago': nuevo.estado_pago(propuesto) or '—', 'Estado operativo': nuevo.estado_operativo(propuesto) or '—',
            'Campos a completar': '; '.join('%s = %s' % (k, v) for k, v in cambios.items()) or '—',
            'Observaciones': ' '.join(alertas) or '—',
            '¿Cuadra?': 'Revisar' if alertas else 'Sí',
            '_cambios': cambios,
        })
    return filas


def escribir_excel(filas, salida):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    libro = Workbook()
    resumen = libro.active
    resumen.title = 'Resumen'
    negrita, cab = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='1D4ED8')
    total = len(filas)
    revisar = sum(f['¿Cuadra?'] == 'Revisar' for f in filas)
    resumen.append(['Revisión de migración · Cotizaciones old → Cotizaciones'])
    resumen['A1'].font = Font(bold=True, size=14)
    resumen.append([])
    for etiqueta, valor in (('Cotizaciones', total), ('Cuadran', total - revisar), ('Para revisar', revisar),
                            ('Con campos a completar', sum(bool(f['_cambios']) for f in filas)),
                            ('Monto total (Sub total + FEE)', round(sum(f['Sub total + FEE'] for f in filas), 2))):
        resumen.append([etiqueta, valor])
    resumen.append([])
    resumen.append(['Pestaña old', 'Pestaña nueva (principal)', 'Cantidad', 'Monto'])
    for celda in resumen[resumen.max_row]:
        celda.font, celda.fill = negrita, cab
    cruce, montos = Counter(), defaultdict(float)
    for f in filas:
        par = (f['Pestaña old'].split(' + ')[0], f['Pestaña(s) nueva(s)'].split(' + ')[0])
        cruce[par] += 1
        montos[par] += f['Sub total + FEE']
    for (a, b), n in sorted(cruce.items()):
        resumen.append([a, b, n, round(montos[(a, b)], 2)])
    resumen.append([])
    resumen.append(['Estado de pago', 'Cantidad'])
    for celda in resumen[resumen.max_row]:
        celda.font, celda.fill = negrita, cab
    for estado, n in Counter(f['Estado de pago'] for f in filas).most_common():
        resumen.append([estado, n])
    resumen.append([])
    resumen.append(['Estado operativo', 'Cantidad'])
    for celda in resumen[resumen.max_row]:
        celda.font, celda.fill = negrita, cab
    for estado, n in Counter(f['Estado operativo'] for f in filas).most_common():
        resumen.append([estado, n])
    for col, ancho in zip('ABCD', (36, 28, 12, 16)):
        resumen.column_dimensions[col].width = ancho

    columnas = [k for k in filas[0] if not k.startswith('_')] if filas else []
    for titulo, lista in (('Detalle', filas), ('Para revisar', [f for f in filas if f['¿Cuadra?'] == 'Revisar'])):
        hoja = libro.create_sheet(titulo)
        hoja.append(columnas)
        for celda in hoja[1]:
            celda.font, celda.fill = negrita, cab
            celda.alignment = Alignment(wrap_text=True, vertical='center')
        amarillo = PatternFill('solid', fgColor='FEF3C7')
        for f in lista:
            hoja.append([f[c] for c in columnas])
            if f['¿Cuadra?'] == 'Revisar':
                hoja.cell(hoja.max_row, columnas.index('¿Cuadra?') + 1).fill = amarillo
        for n, c in enumerate(columnas, 1):
            hoja.column_dimensions[get_column_letter(n)].width = {'Observaciones': 70, 'Campos a completar': 50,
                                                                  'Motivo / objetivo': 40, 'Site': 26}.get(c, 18)
        if columnas:
            hoja.cell(1, columnas.index('Sub total + FEE') + 1)
            for fila in hoja.iter_rows(min_row=2, min_col=columnas.index('Sub total + FEE') + 1, max_col=columnas.index('Sub total + FEE') + 1):
                fila[0].number_format = '"S/" #,##0.00'
        hoja.freeze_panes = 'C2'
        hoja.auto_filter.ref = hoja.dimensions
    libro.save(salida)


def main(argv):
    from app import app
    with app.app_context():
        if argv[0] == '--db':
            from models import NucleusData, Proyecto
            def leer(nombre):
                p = Proyecto.query.filter_by(nombre=nombre).first()
                return [{'id': r.id, 'key_value': r.key_value, 'data_json': r.data_json}
                        for r in NucleusData.query.filter_by(proyecto_id=p.id)] if p else []
            cot, rend, salida = leer('Cotizaciones'), leer('Rendicion'), argv[1]
        else:
            cot = json.load(open(argv[0], encoding='utf-8'))
            rend = json.load(open(argv[1], encoding='utf-8'))
            salida = argv[2]
        filas = analizar(cot, rend)
    escribir_excel(filas, salida)
    print('%d cotizaciones · %d para revisar → %s' % (len(filas), sum(f['¿Cuadra?'] == 'Revisar' for f in filas), salida))


if __name__ == '__main__':
    main(sys.argv[1:])
