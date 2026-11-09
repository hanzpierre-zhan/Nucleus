"""Cot_New: vista de Cotizaciones con el diseño de Caja Chica (pestañas, tuerca, tabla y detalle).

Lee las mismas filas del módulo Cotizaciones (NucleusData); no duplica datos. Las acciones
que ya existen se reutilizan desde /api/cotizacion/accion.
"""
import io
import json
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, render_template, request, send_file, session

from models import NucleusData, Proyecto
from services import get_menu_proyectos, login_required
from services.utilidades import puede_cotizaciones

bp = Blueprint('cot_new', __name__)

# Pestañas en el orden del flujo: (clave, nombre, icono, color)
PESTANAS = (
    ('registro', 'Registro', 'fa-pen-to-square', '#64748b'),
    ('cliente', 'Cliente', 'fa-user-check', '#f08a1c'),
    ('sustentar', 'Sustentar', 'fa-camera', '#2563eb'),
    ('atendido', 'Atendido', 'fa-circle-check', '#16a34a'),
    ('proveedor', 'Proveedor', 'fa-file-invoice', '#7c3aed'),
    ('transito', 'Tránsito', 'fa-shoe-prints', '#0891b2'),
    ('cancelado', 'Anulado', 'fa-ban', '#94a3b8'),
)
ESTADO_PESTANA = {
    'pdt. cotización': 'registro', 'pdt. cotizacion': 'registro',
    'en aprobación': 'cliente', 'en aprobacion': 'cliente', 'cotizado': 'cliente',
    'aprobado': 'sustentar', 'sustentar': 'sustentar',
    'atendido': 'atendido', 'validado': 'atendido',
    'cancelado': 'cancelado', 'anulado': 'cancelado', 'anulada': 'cancelado',
}
# Campos que viajan a la pantalla (sin fotos, sustentos ni historial pesado).
CAMPOS = ('N° ORDEN', 'N° COTIZACION', 'FECHA', 'CLIENTE', 'SUPERVISOR', 'NOMBRE SITE', 'NUMERO WO', 'MOTIVO',
          'OBJETIVO', 'DEPARTAMENTO', 'TIPO DE GASTO', 'TIPO DE COTIZACION', 'SUB TOTAL + FEE', 'ESTADO COTIZACION',
          'GESTOR', 'SOLICITADO POR', 'COTIZADO POR', 'FECHA COTIZADO', 'FECHA ENVIO CLIENTE', 'FECHA APROBACION',
          'TIPO GASTO APROBACION', 'NOMBRE DE PROVEEDOR', 'NUMERO FACTURA PROVEEDOR', 'NUMERO OC PROVEEDOR',
          'SUBTOTAL FACTURA PROVEEDOR', 'MOTIVO RECHAZO', 'FECHA RECHAZO', 'MOTIVO CANCELACION', 'FECHA CANCELACION',
          'CODIGO INTERNO', 'COMENTARIO APROBACION', 'ITEMS_JSON')


def _proyecto():
    modulo = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not modulo:
        abort(404)
    if not puede_cotizaciones(session.get('user_id'), session.get('rol'), session.get('current_proyecto_nombre')):
        abort(403)
    return modulo


def pestana_de(datos):
    return ESTADO_PESTANA.get(str(datos.get('ESTADO COTIZACION') or '').strip().lower(), 'registro')


def en_proveedor(datos):
    """Aprobada para proveedor y aún sin sus documentos completos (misma regla que Cotizaciones)."""
    if str(datos.get('TIPO GASTO APROBACION') or '').strip().casefold() != 'proveedor':
        return False
    if pestana_de(datos) not in ('sustentar', 'atendido'):
        return False
    try:
        subtotal_ok = Decimal(str(datos.get('SUBTOTAL FACTURA PROVEEDOR') or '').strip()) >= 0
    except InvalidOperation:
        subtotal_ok = False
    documentos = all(str(datos.get(c) or '').strip() for c in
                     ('NUMERO FACTURA PROVEEDOR', 'NUMERO OC PROVEEDOR', 'ADJUNTO FACTURA PROVEEDOR'))
    return not (documentos and subtotal_ok)


def _monto(datos):
    from services.rendicion_presupuesto_cotizacion import monto_cotizacion
    return monto_cotizacion(datos.get('SUB TOTAL + FEE'), datos.get('ITEMS_JSON'))


def _filas():
    modulo = _proyecto()
    from services.cotizacion_transito import indice_transito
    from services.rendicion_presupuesto_cotizacion import proyecto as familia_cotizacion
    transito = indice_transito()
    filas = []
    for rid, key, crudo in (NucleusData.query.filter_by(proyecto_id=modulo.id)
                            .with_entities(NucleusData.id, NucleusData.key_value, NucleusData.data_json)
                            .order_by(NucleusData.id.desc())):
        try:
            datos = json.loads(crudo or '{}')
        except ValueError:
            continue
        fila = {c: datos.get(c, '') for c in CAMPOS}
        try:
            fila['items'] = json.loads(datos.get('ITEMS_JSON') or '[]')
        except (TypeError, ValueError):
            fila['items'] = []
        fila.pop('ITEMS_JSON', None)
        pestanas = [pestana_de(datos)]
        if en_proveedor(datos):
            pestanas.append('proveedor')
        if transito.get(key):
            pestanas.append('transito')
        fila.update(id=rid, key=key, pestanas=pestanas, monto=_monto(datos) or '0.00',
                    familia=familia_cotizacion(datos) or str(datos.get('CLIENTE') or '').strip().upper(),
                    transito=transito.get(key))
        filas.append(fila)
    return modulo, filas


@bp.get('/cot-new/')
@login_required
def pagina():
    modulo = _proyecto()
    rol = str(session.get('rol') or '').strip().lower()
    return render_template('cot_new.html', pestanas=PESTANAS, proyecto_id=modulo.id,
                           puede_gestionar=rol not in ('demo', 'contrata'),
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')))


@bp.get('/api/cot-new/lista')
@login_required
def lista():
    _, filas = _filas()
    return jsonify(cotizaciones=filas)


@bp.post('/api/cot-new/exportar')
@login_required
def exportar():
    """Excel de las cotizaciones elegidas (la pestaña o todo), con los filtros que se ven."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    ids = request.get_json(silent=True)
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10000 or any(type(i) is not int for i in ids):
        return jsonify(error='Selecciona cotizaciones válidas para exportar.'), 400
    _, filas = _filas()
    por_id = {f['id']: f for f in filas}
    nombres = {p[0]: p[1] for p in PESTANAS}
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Cotizaciones'
    columnas = ('N° COTIZACION', 'FECHA', 'CLIENTE', 'SUPERVISOR', 'NOMBRE SITE', 'NUMERO WO', 'MOTIVO',
                'ESTADO COTIZACION', 'GESTOR', 'SOLICITADO POR', 'COTIZADO POR', 'TIPO DE GASTO', 'TIPO GASTO APROBACION')
    hoja.append(['Pestaña', *columnas, 'Sub total + FEE'])
    for i in ids:
        fila = por_id.get(i)
        if not fila:
            continue
        valores = [nombres[fila['pestanas'][0]], *(str(fila.get(c) or '') for c in columnas), Decimal(fila['monto'])]
        hoja.append([ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v for v in valores])
        hoja.cell(hoja.max_row, len(valores)).number_format = '#,##0.00'
    hoja.freeze_panes = 'A2'
    hoja.auto_filter.ref = hoja.dimensions
    for columna in hoja.columns:
        titulo = columna[0]
        titulo.font = Font(bold=True, color='FFFFFF')
        titulo.fill = PatternFill('solid', fgColor='166534')
        hoja.column_dimensions[get_column_letter(titulo.column)].width = min(40, max(10, *(len(str(c.value or '')) + 2 for c in columna)))
    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    return send_file(archivo, as_attachment=True, download_name='Cotizaciones.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
