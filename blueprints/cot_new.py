"""Cot_New: vista de Cotizaciones con el diseño de Caja Chica (pestañas, tuerca, tabla y detalle).

Lee las mismas filas del módulo Cotizaciones (NucleusData); no duplica datos. Las acciones
que ya existen se reutilizan desde /api/cotizacion/accion.
"""
import io
import json
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, render_template, request, send_file, session

from db import db
from models import NucleusData, Proyecto
from services import get_menu_proyectos, login_required
from services.utilidades import puede_cotizaciones

bp = Blueprint('cot_new', __name__)

# Pestañas en el orden del flujo: (clave, nombre, icono, color)
PESTANAS = (
    ('registro', 'Registro', 'fa-pen-to-square', '#64748b'),
    ('cliente', 'Cliente', 'fa-user-check', '#f08a1c'),
    ('cajachica', 'Caja chica', 'fa-wallet', '#16a34a'),
    ('transito', 'Tránsito', 'fa-shoe-prints', '#0891b2'),
    ('proveedor', 'Proveedor', 'fa-file-invoice', '#7c3aed'),
    ('sustentar', 'Operaciones', 'fa-screwdriver-wrench', '#2563eb'),
    ('atendido', 'Atendido', 'fa-circle-check', '#16a34a'),
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
CAMPOS = ('N° ORDEN', 'N° COTIZACION', 'FECHA', 'CLIENTE', 'NOMBRE CLIENTE', 'SUPERVISOR', 'NOMBRE SITE', 'NUMERO WO', 'MOTIVO',
          'OBJETIVO', 'DEPARTAMENTO', 'TIPO DE GASTO', 'TIPO DE COTIZACION', 'SUB TOTAL + FEE', 'ESTADO COTIZACION',
          'GESTOR', 'SOLICITADO POR', 'COTIZADO POR', 'FECHA COTIZADO', 'FECHA ENVIO CLIENTE', 'FECHA APROBACION',
          'TIPO GASTO APROBACION', 'NOMBRE DE PROVEEDOR', 'NUMERO FACTURA PROVEEDOR', 'NUMERO OC PROVEEDOR',
          'SUBTOTAL FACTURA PROVEEDOR', 'MOTIVO RECHAZO', 'FECHA RECHAZO', 'MOTIVO CANCELACION', 'FECHA CANCELACION',
          'CODIGO INTERNO', 'COMENTARIO APROBACION', 'ITEMS_JSON', 'ADJUNTO CORREO CLIENTE', 'NOMBRE CORREO CLIENTE',
          'ADJUNTO COTIZACION PROVEEDOR', 'ADJUNTO FACTURA PROVEEDOR', '_PROVEEDOR_REGISTROS', '_SUSTENTO_APROBADO',
          'OBSERVACION SUSTENTO', 'FECHA ATENCION', 'GENERADA', 'TIPO DE CONCEPTO', 'PROYECTO FLM', 'CODIGO SITE',
          'DISTRITO', 'PROVINCIA', 'REGION', 'COTIZADOR', 'COTIZADOR USUARIO', 'FECHA PAGO', 'FOTO PAGO', 'PAGADO POR',
          'MONTO PAGADO', '_PAGO_PENDIENTE', '_TRANSITO_A_PROVEEDOR', 'MONTO TRANSITO', 'PROVISION')


def _proyecto():
    modulo = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not modulo:
        abort(404)
    if not puede_cotizaciones(session.get('user_id'), session.get('rol'), session.get('current_proyecto_nombre')):
        abort(403)
    return modulo


def pestana_de(datos):
    return ESTADO_PESTANA.get(str(datos.get('ESTADO COTIZACION') or '').strip().lower(), 'registro')


def tipo_atencion(datos):
    """Caja Chica, Proveedor o Tránsito (cómo se atiende la cotización aprobada)."""
    t = str(datos.get('TIPO GASTO APROBACION') or '').strip().casefold()
    return {'caja chica': 'Caja Chica', 'proveedor': 'Proveedor', 'transito': 'Tránsito', 'tránsito': 'Tránsito'}.get(t, '')


def documentos_proveedor(datos):
    """Factura, OC, subtotal y archivo de la factura completos."""
    try:
        subtotal_ok = Decimal(str(datos.get('SUBTOTAL FACTURA PROVEEDOR') or '').strip()) >= 0
    except InvalidOperation:
        subtotal_ok = False
    return subtotal_ok and all(str(datos.get(c) or '').strip() for c in
                               ('NUMERO FACTURA PROVEEDOR', 'NUMERO OC PROVEEDOR', 'ADJUNTO FACTURA PROVEEDOR'))


def por_pagar(datos):
    """Aprobada con el flujo de pago y aún sin pagar (las aprobadas antes del flujo se toman como pagadas)."""
    return pestana_de(datos) == 'sustentar' and bool(datos.get('_PAGO_PENDIENTE'))


def en_proveedor(datos):
    """Pestaña Proveedor: por pagar al proveedor, o pagada (tránsito o anterior) y sin sus documentos completos."""
    if pestana_de(datos) not in ('sustentar', 'atendido'):
        return False
    tipo = tipo_atencion(datos)
    if tipo == 'Proveedor':
        return por_pagar(datos) or not documentos_proveedor(datos)
    return (tipo == 'Tránsito' and not por_pagar(datos) and bool(datos.get('_TRANSITO_A_PROVEEDOR'))
            and not documentos_proveedor(datos))


def aprobada(datos):
    """Ya la aprobó el cliente (desde ahí corren el estado de pago y el operativo)."""
    return pestana_de(datos) in ('sustentar', 'atendido')


def estado_pago(datos):
    """Pendiente Depósito, Depositado Caja Chica, Depositado sin proveedor o Facturado Proveedor."""
    if not aprobada(datos):
        return ''
    tipo = tipo_atencion(datos)
    if tipo in ('Proveedor', 'Tránsito') and documentos_proveedor(datos):
        return 'Facturado Proveedor'
    if por_pagar(datos) or tipo == 'Proveedor':
        return 'Pendiente Depósito'
    return 'Depositado sin proveedor' if tipo == 'Tránsito' else 'Depositado Caja Chica'


def estado_operativo(datos):
    """Pdt. ejecutar, En ejecución, Ejecutado en campo (fechas de la ficha) o Sustentado (pasó a Atendido)."""
    if not aprobada(datos):
        return ''
    if pestana_de(datos) == 'atendido':
        return 'Sustentado'
    import re
    wos = [w.strip().casefold() for w in re.split(r'[,;|\n]+', str(datos.get('NUMERO WO') or '')) if w.strip()]
    ejecucion = datos.get('_EJECUCION_WO') if isinstance(datos.get('_EJECUCION_WO'), dict) else {}
    if len(wos) <= 1:
        unica = ejecucion.get(wos[0], {}) if wos else {}
        fechas = [{'inicio': str(datos.get('INICIO EJECUCION') or unica.get('inicio') or '').strip(),
                   'fin': str(datos.get('FIN EJECUCION') or unica.get('fin') or '').strip()}]
    else:
        fechas = [ejecucion.get(w, {}) for w in wos]
    if all(f.get('fin') for f in fechas):
        return 'Ejecutado en campo'
    if any(f.get('inicio') or f.get('fin') for f in fechas):
        return 'En ejecución'
    return 'Pdt. ejecutar'


def pestanas_de(datos):
    """Caja chica o Proveedor hasta pagar; luego Operaciones (con Tránsito o Proveedor en paralelo)."""
    base = pestana_de(datos)
    if por_pagar(datos):
        return ['proveedor'] if tipo_atencion(datos) == 'Proveedor' else ['cajachica']
    pestanas = [base]
    if (base in ('sustentar', 'atendido') and tipo_atencion(datos) == 'Tránsito'
            and not datos.get('_TRANSITO_A_PROVEEDOR') and datos.get('FECHA PAGO')):
        pestanas.append('transito')
    if en_proveedor(datos):
        pestanas.append('proveedor')
    return pestanas


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
        pestanas = pestanas_de(datos)
        fila.update(estado_pago=estado_pago(datos), estado_operativo=estado_operativo(datos))
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
    return render_template('cot_new.html', pestanas=PESTANAS, proyecto_id=modulo.id, tipos_concepto=TIPOS_CONCEPTO,
                           cotizadores=[{'nombre': n, 'usuario': u} for n, u in COTIZADORES],
                           nombres_cliente=NOMBRES_CLIENTE, supervisores=SUPERVISORES,
                           proyectos_flm=PROYECTOS_FLM,
                           puede_gestionar=rol not in ('demo', 'contrata'),
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')))


@bp.get('/api/cot-new/lista')
@login_required
def lista():
    _, filas = _filas()
    return jsonify(cotizaciones=filas, usuarios=_nombres_usuarios())


def _nombres_usuarios():
    """Usuario de Nucleus → nombre completo, para mostrar nombres legibles en vez del usuario."""
    from models import Usuario
    return {u.lower(): n.strip() for u, n in Usuario.query.with_entities(Usuario.username, Usuario.nombre) if u and (n or '').strip()}


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
    columnas = ('N° COTIZACION', 'FECHA', 'CLIENTE', 'NOMBRE CLIENTE', 'SUPERVISOR', 'NOMBRE SITE', 'NUMERO WO', 'MOTIVO',
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


def _fijar_cotizaciones():
    """Crear y generar reutilizan los servicios de Cotizaciones, que trabajan sobre el módulo de la sesión."""
    modulo = _proyecto()
    session.pop('flm_resource_context', None)
    session['current_proyecto_id'], session['current_proyecto_nombre'] = int(modulo.id), modulo.nombre


@bp.post('/api/cot-new/agregar')
@login_required
def agregar():
    """Nueva cotización: mismo alta de Cotizaciones (numeración, GESTOR y validaciones)."""
    _fijar_cotizaciones()
    from blueprints.rows import api_rows_add
    return api_rows_add()


@bp.post('/api/cot-new/guardar')
@login_required
def guardar():
    """Editor: guarda motivo, objetivo, FEE e ítems de una cotización ya registrada."""
    _fijar_cotizaciones()
    from blueprints.rows import api_rows_bulk_update
    datos = request.get_json(silent=True) or {}
    permitidos = ('MOTIVO', 'OBJETIVO', 'SUPERVISOR', 'NUMERO WO', 'NOMBRE SITE', 'ITEMS_JSON', 'SUB TOTAL + FEE')
    return api_rows_bulk_update({'key': datos.get('key'), 'data': {k: v for k, v in (datos.get('data') or {}).items() if k in permitidos}})


def _fila_cotizacion(key):
    modulo = _proyecto()
    fila = (NucleusData.query.filter_by(proyecto_id=modulo.id, key_value=str(key or '').strip())
            .with_for_update().first())
    if not fila:
        abort(404)
    return modulo, fila, json.loads(fila.data_json or '{}')


def _guardar(fila, datos, accion, usuario, detalle=''):
    """Guarda con historial y anota el movimiento; devuelve la fecha y hora de Perú."""
    from datetime import datetime, timedelta
    from models import NucleusHistory
    db.session.add(NucleusHistory(proyecto_id=fila.proyecto_id, key_value=fila.key_value, data_json=fila.data_json))
    ahora = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')
    datos.setdefault('_MOVIMIENTOS_PAGO', []).append({'accion': accion, 'por': usuario, 'fecha': ahora, 'detalle': detalle})
    if accion == 'pagar':
        datos['FECHA PAGO'] = ahora
    fila.data_json = json.dumps(datos, ensure_ascii=False)
    db.session.commit()
    return ahora


def _puede_mover():
    return str(session.get('rol') or '').strip().lower() not in ('demo', 'contrata')


def _usuario():
    from services.utilidades import audit_user
    return audit_user() or 'Desconocido'


@bp.post('/api/cot-new/pagar')
@login_required
def pagar():
    """Registra el pago (foto; fecha y hora automáticas) y la cotización pasa a Operaciones."""
    if not _puede_mover():
        return jsonify(error='No tienes permisos para registrar pagos.'), 403
    entrada = request.get_json(silent=True) or {}
    modulo, fila, datos = _fila_cotizacion(entrada.get('key'))
    if not por_pagar(datos):
        return jsonify(error='Esta cotización no está pendiente de pago.'), 409
    from werkzeug.utils import secure_filename
    foto = str(entrada.get('foto') or '').strip()
    prefijo = '/api/cotizacion/correo/%d/%s/pago_' % (modulo.id, secure_filename(fila.key_value))
    if not foto.startswith(prefijo) or any(c in foto for c in '<>"\'\\'):
        return jsonify(error='Adjunta la foto del pago.'), 400
    if tipo_atencion(datos) == 'Proveedor' and not documentos_proveedor(datos):
        return jsonify(error='Carga primero la factura y la OC del proveedor.'), 409
    usuario = _usuario()
    datos.pop('_PAGO_PENDIENTE', None)
    datos.update({'FOTO PAGO': foto, 'PAGADO POR': usuario, 'MONTO PAGADO': _monto(datos) or ''})
    if tipo_atencion(datos) == 'Tránsito':
        # Se paga lo definido para Tránsito; la provisión (20 % de ese monto) pasa luego a proveedor.
        from services.cotizacion_transito import monto_transito, provision
        monto = monto_transito(datos.get('MONTO TRANSITO'))
        if monto is None:
            return jsonify(error='Falta el monto a depositar para Tránsito.'), 409
        datos.update({'MONTO PAGADO': monto, 'PROVISION': provision(monto)})
    _guardar(fila, datos, 'pagar', usuario, foto)
    return jsonify(success=True, pestanas=pestanas_de(datos))


# Cambios permitidos entre bandejas: (desde, hacia).
MOVIMIENTOS = {('cajachica', 'transito'), ('cajachica', 'proveedor'), ('proveedor', 'cajachica'), ('transito', 'proveedor')}


@bp.post('/api/cot-new/mover')
@login_required
def mover():
    """Pasa la cotización entre Caja chica, Proveedor y Tránsito."""
    if not _puede_mover():
        return jsonify(error='No tienes permisos para mover cotizaciones.'), 403
    entrada = request.get_json(silent=True) or {}
    _, fila, datos = _fila_cotizacion(entrada.get('key'))
    desde, hacia = str(entrada.get('desde') or ''), str(entrada.get('hacia') or '')
    if (desde, hacia) not in MOVIMIENTOS or desde not in pestanas_de(datos):
        return jsonify(error='Ese cambio no aplica a esta cotización.'), 409
    if desde == 'transito':
        datos['_TRANSITO_A_PROVEEDOR'] = '1'
        datos['_PROVEEDOR_PARALELO'] = True
    elif desde == 'proveedor' and not por_pagar(datos):
        # Ya pagada (viene de Tránsito): no se encontró proveedor y queda como Caja chica; sigue en Operaciones.
        datos['TIPO GASTO APROBACION'] = 'Caja Chica'
        datos['_PROVEEDOR_PARALELO'] = False
        datos.pop('_TRANSITO_A_PROVEEDOR', None)
    else:
        nuevo = {'transito': 'Tránsito', 'proveedor': 'Proveedor', 'cajachica': 'Caja Chica'}[hacia]
        if nuevo == tipo_atencion(datos):
            return jsonify(error='Ya está como ' + nuevo + '.'), 409
        if nuevo == 'Tránsito':
            from services.cotizacion_transito import monto_transito
            monto = monto_transito(entrada.get('monto_transito'))
            if monto is None:
                return jsonify(error='Escribe el monto a depositar para Tránsito (mayor a 0).'), 400
            datos['MONTO TRANSITO'] = monto
        else:
            datos.pop('MONTO TRANSITO', None)
        datos['TIPO GASTO APROBACION'] = nuevo
        datos['_PROVEEDOR_PARALELO'] = nuevo == 'Proveedor'
    _guardar(fila, datos, 'mover', _usuario(), desde + ' -> ' + hacia)
    return jsonify(success=True, pestanas=pestanas_de(datos))


@bp.post('/api/cot-new/generar')
@login_required
def generar():
    """Marca la cotización como generada y devuelve su PDF (mismo servicio de Cotizaciones)."""
    _fijar_cotizaciones()
    from blueprints.cotizacion import api_cotizacion_registro_generar
    return api_cotizacion_registro_generar()


# ── Nuevo registro: proyecto FLM, site registrado (con sus datos) y WO registrados ──
PROYECTOS_FLM = ('FLM - CLARO', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - PEXT')
# PEXT no tiene sites propios en la base de sites: usa los de Entel (por confirmar con el usuario).
SITES_DE = {'FLM - PEXT': 'FLM - ENTEL'}
CAMPOS_SITE_WO = ('Site Name', 'Site ID', 'Nombre de Site', 'Código Site', 'Site Id', 'Site Id Name', 'Site')
# Cotizadores que se asignan al registrar (nombre y usuario de Nucleus, como figuran en Usuarios).
COTIZADORES = (('Luciano Aracca', 'laracca'), ('Diego Rodriguez', 'drodriguez'), ('Ricardo Huaman', 'rhuaman'), ('Edwin Lopez', 'elopez'))
# Supervisores (lista de Cotizaciones, con el nombre homologado: Nombre Apellido).
SUPERVISORES = ('Jordan Gonzales', 'Dennis Quispe', 'Jesus Sotelo', 'Roberto Encarnacion', 'Eloy Huancapaza', 'Dennis Unton', 'Edwin Lopez')
# Contactos del cliente que se eligen al registrar la cotización, según el proyecto.
NOMBRES_CLIENTE = {
    'ENTEL': ('George McCloun', 'Sergio Huaman', 'Even Junior Vivar'),
    'PEXT': ('Marco Gomez',),
    'INTEGRATEL': ('Daivis Mendoza',),
    'CLARO': ('Percy Huaman', 'Carlos Ocana', 'Giancarlo Saldarriaga', 'Giancarlo Costa', 'Ernesto Rojas'),
}
TIPOS_CONCEPTO = ('Servicio', 'Alquiler', 'Acarreo', 'Compras y suministros', 'Desplazamiento fuera de zona',
                  'Transporte fluvial', 'Custodio y resguardo', 'Personal y mano de obra')


def _site(datos):
    return {'site': str(datos.get('Site') or datos.get('Nombre del sitio | Site name') or '').strip(),
            'nombre': str(datos.get('Nombre del sitio | Site name') or '').strip(),
            'codigo': str(datos.get('Código del sitio | Site ID') or '').strip(),
            'distrito': str(datos.get('Distrito | District') or '').strip(),
            'provincia': str(datos.get('Provincia | Provincia') or '').strip(),
            'region': str(datos.get('Region | Region') or '').strip()}


@bp.get('/api/cot-new/sites')
@login_required
def sites():
    """Sites registrados del proyecto, buscando por nombre o código (máximo 30)."""
    _proyecto()
    from services.alcance_proyectos import _valor
    proyecto = request.args.get('proyecto', '')
    if proyecto not in PROYECTOS_FLM:
        return jsonify(error='Elige un proyecto FLM.'), 400
    modulo = Proyecto.query.filter_by(nombre='SITE').first()
    if not modulo:
        return jsonify(sites=[])
    texto = str(request.args.get('q') or '').strip()
    raw = NucleusData.data_json
    consulta = NucleusData.query.filter(NucleusData.proyecto_id == modulo.id,
                                        _valor(raw, 'Proyecto') == SITES_DE.get(proyecto, proyecto))
    if texto:
        patron = '%' + texto.replace('%', '') + '%'
        consulta = consulta.filter(NucleusData.data_json.ilike(patron))
    resultado = []
    for (crudo,) in consulta.with_entities(NucleusData.data_json).limit(30):
        try:
            resultado.append(_site(json.loads(crudo or '{}')))
        except ValueError:
            continue
    return jsonify(sites=resultado)


@bp.get('/api/cot-new/wos')
@login_required
def wos():
    """WO registrados en el FLM del proyecto para ese site (por código o nombre del site)."""
    _proyecto()
    proyecto = request.args.get('proyecto', '')
    if proyecto not in PROYECTOS_FLM:
        return jsonify(error='Elige un proyecto FLM.'), 400
    claves = [c for c in (str(request.args.get('codigo') or '').strip(), str(request.args.get('nombre') or '').strip()) if c]
    modulo = Proyecto.query.filter_by(nombre=proyecto).first()
    texto = str(request.args.get('q') or '').strip().replace('%', '')
    if modulo and (texto or not claves):
        # Búsqueda por número (o, sin texto ni site, los WO más recientes del proyecto).
        consulta = NucleusData.query.filter(NucleusData.proyecto_id == modulo.id, ~NucleusData.key_value.like('WO-TEMP-%'))
        if texto:
            consulta = consulta.filter(NucleusData.key_value.ilike('%' + texto + '%'))
        encontrados = consulta.with_entities(NucleusData.key_value).order_by(NucleusData.id.desc()).limit(25)
        return jsonify(wos=[k for (k,) in encontrados])
    if not modulo or not claves:
        return jsonify(wos=[])
    from sqlalchemy import or_
    consulta = (NucleusData.query.filter(NucleusData.proyecto_id == modulo.id,
                                         or_(*[NucleusData.data_json.ilike('%' + c.replace('%', '') + '%') for c in claves]))
                .with_entities(NucleusData.key_value, NucleusData.data_json).order_by(NucleusData.id.desc()).limit(300))
    buscadas = {c.upper() for c in claves}
    resultado = []
    for key, crudo in consulta:
        try:
            datos = json.loads(crudo or '{}')
        except ValueError:
            continue
        valores = {str(datos.get(c) or '').strip().upper() for c in CAMPOS_SITE_WO}
        if valores & buscadas or any(b in v for b in buscadas for v in valores if v):
            if not str(key).startswith('WO-TEMP-'):
                resultado.append(str(key))
    return jsonify(wos=list(dict.fromkeys(resultado))[:60])
