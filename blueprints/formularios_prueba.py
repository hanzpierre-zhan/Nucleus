"""Dos formularios móviles en paralelo al flujo real de Google Forms."""
import hashlib
import hmac
import io
import json
import re
import secrets
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import unquote, urlsplit

from flask import (Blueprint, abort, current_app, g, jsonify, redirect,
                   render_template, request, send_file, session, url_for)
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

from models import AccesoProyecto, Proyecto, Usuario
from services import login_required
from services import formularios_prueba as piloto
from services import claves_tecnico as claves
from services.recursos_flm import FLM_NOMBRES, familia

bp = Blueprint('form_pruebas', __name__, url_prefix='/form-pruebas')
ROLES_ADMIN_PILOTO = ('zeno', 'suport', 'admin')
PROYECTOS = ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT')
COBRA = 'Gasto Cobra'
REFACTURABLE = 'Refacturable'
# Categoría, detalle, etiqueta, clasificación general o por proyecto, criterio.
CATALOGO_GASTOS = (
    ('PEAJE', '', 'Peajes', COBRA, 'Pago en casetas de peaje durante el viaje de ida o vuelta al site.'),
    ('COMPRAS', 'Consumibles', 'Compra de consumibles', COBRA, 'Solo consumibles. Las piezas y repuestos tienen su propia opción.'),
    ('MATERIALES', '', 'Compra de materiales y/o repuestos',
     {'ENTEL': REFACTURABLE, 'INTEGRATEL': COBRA, 'CLARO': COBRA},
     'Piezas para instalar o reemplazar, como cables, conectores o repuestos de un equipo.'),
    ('COMPRAS', 'Equipos especiales de medición', 'Compra de equipos especiales de medición', COBRA,
     'Telurómetros, laptops, celulares y equipos de medición eléctrica o electrónica.'),
    ('COMPRAS', 'Accesorios', 'Compra de accesorios', COBRA, 'Accesorios eléctricos, electrónicos y de cómputo.'),
    ('ALQUILER', 'Vehículos - Costo Cobra', 'Alquiler de vehículos - Costo Cobra', COBRA,
     'Camioneta, auto o camión alquilado para el trabajo cuando Cobra asume el costo.'),
    ('ALQUILER', 'Vehículos - Refacturable', 'Alquiler de vehículos - Refacturable', REFACTURABLE,
     'Camioneta, auto o camión alquilado para el trabajo cuando corresponde cobrarlo al cliente.'),
    ('ALQUILER', 'Herramientas', 'Alquiler de herramientas', COBRA, 'Taladros, alicates, desarmadores, etc.'),
    ('ALQUILER', 'Equipos especiales de medición', 'Alquiler de equipos especiales de medición', COBRA,
     'Telurómetros, megóhmetros, laptops, etc.'),
    ('ALQUILER', 'Generadores eléctricos - Refacturable', 'Alquiler de generadores eléctricos - Refacturable',
     REFACTURABLE, 'Consulta con el gestor si corresponde a costo Cobra.'),
    ('ALQUILER', 'Generadores eléctricos - Costo Cobra', 'Alquiler de generadores eléctricos - Costo Cobra',
     COBRA, 'Consulta con el gestor si corresponde a costo Cobra.'),
    ('PASAJE', 'Local - Costo Cobra', 'Movilidad local - Costo Cobra', COBRA, 'Traslado en moto o bus.'),
    ('PASAJE', 'Local o interprovincial - Refacturable', 'Movilidad local o interprovincial - Refacturable',
     REFACTURABLE, 'Traslado en moto o bus.'),
    ('VIATICOS', '', 'Viáticos', COBRA, 'Hospedaje y alimentación.'),
    ('COCHERA', '', 'Cochera o estacionamiento', COBRA, 'Pago por estacionar o resguardar el vehículo de trabajo.'),
    ('ACARREO', '', 'Servicio de acarreo', REFACTURABLE,
     'Traslado de equipos o materiales en el tramo final, por ejemplo, llevar baterías desde el vehículo hasta el site.'),
    ('CUSTODIO', '', 'Servicio de custodio', REFACTURABLE,
     'Vigilancia o acompañamiento para proteger al personal, los equipos o los materiales.'),
    ('COMBUSTIBLE', '', 'Combustible', COBRA, 'Gasolina o diésel para el vehículo, generador o equipo usado en el trabajo.'),
    ('FLETE Y ENVÍOS', '', 'Flete y envíos logísticos', COBRA,
     'Transporte de carga o paquetería entre ubicaciones, como enviar repuestos del almacén al site.'),
    ('MANTENIMIENTO VEHICULAR', '', 'Mantenimiento vehicular', COBRA,
     'Servicio de taller para el vehículo de trabajo, como cambio de aceite o reparación de neumáticos.'),
    ('REPARACIÓN DE EQUIPOS', '', 'Reparación de equipos especiales (GE)',
     {'ENTEL': COBRA, 'INTEGRATEL': REFACTURABLE, 'CLARO': REFACTURABLE, 'PEXT': REFACTURABLE},
     'Generadores, laptops y equipos de medición, entre otros.'),
    ('SERVICIOS DE TERCEROS', '', 'Servicios de terceros', REFACTURABLE, 'Mano de obra de un tercero.'),
    ('ACCESOS Y PERMISOS', '', 'Accesos y permisos a sites', REFACTURABLE, 'Cupos o permisos requeridos para ingresar al site.'),
    ('COMUNICACIONES', '', 'Comunicaciones', COBRA, 'Recargas de saldo para coordinar y reportar el trabajo en campo.'),
)
REGLAS_GASTO = {(categoria, detalle): (etiqueta, regla)
                for categoria, detalle, etiqueta, regla, _ in CATALOGO_GASTOS}
GASTOS = tuple(dict.fromkeys(categoria for categoria, *_ in CATALOGO_GASTOS))
ETIQUETAS_GASTO = {
    'PASAJE': 'Pasajes',
    'MATERIAL': 'Compra de materiales',
    'MATERIALES': 'Compra de materiales',
    'VIATICOS': 'Viáticos',
}
DETALLES_GASTO = {
    categoria: tuple(detalle for grupo, detalle in REGLAS_GASTO if grupo == categoria and detalle)
    for categoria, detalle in REGLAS_GASTO if detalle
}
BANCOS = (
    'Scotiabank', 'Interbank', 'BCP', 'BBVA', 'Banco de la Nación',
    'BanBif', 'Banco Pichincha', 'Mibanco', 'Banco Falabella', 'Banco Ripley',
)
def habilitado():
    return bool(current_app.config.get('FORM_PRUEBAS_ENABLED')) or (piloto.raiz() / 'habilitado').is_file()


def csrf():
    if not session.get('form_csrf'):
        session['form_csrf'] = secrets.token_urlsafe(32)
    return session['form_csrf']


def comprobar_csrf():
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
    if not token or not hmac.compare_digest(str(token), str(session.get('form_csrf', ''))):
        abort(403, 'La sesión del formulario venció. Actualiza la página.')


def iniciar_tecnico(person):
    """Identidad exclusiva del portal; nunca crea una cuenta administrativa."""
    session.clear()
    session.update(form_documento=person['documento'], form_personal_id=person['id'], form_login_at=time.time())
    csrf()


@bp.before_app_request
def aislar_sesion_tecnica():
    if session.get('form_documento') and not request.path.startswith(('/form-pruebas', '/static/')):
        if request.method != 'GET' or request.path.startswith('/api/'):
            return jsonify(error='Tu acceso permite únicamente Solicitar y Rendir.'), 403
        return redirect(url_for('form_pruebas.inicio'))


@bp.before_request
def solo_piloto():
    if request.endpoint == 'form_pruebas.administrar':
        return
    if not habilitado():
        abort(404)
    if request.content_length and request.content_length > 32 * 1024 * 1024:
        abort(413, 'Las fotos superan 32 MB. Envía menos fotos o reduce su tamaño.')
    if request.method == 'POST':
        comprobar_csrf()


@bp.after_request
def privado(response):
    response.headers['Cache-Control'] = 'no-store, private'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.endpoint == 'form_pruebas.administrar':
        return response
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; "
        "form-action 'self'; base-uri 'self'; object-src 'none'")
    return response


def tecnico(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        doc = session.get('form_documento', '')
        person = piloto.buscar_personal(doc) if doc else None
        if not person or person['id'] != session.get('form_personal_id') or time.time() - session.get('form_login_at', 0) > 8 * 3600:
            session.pop('form_documento', None)
            session.pop('form_personal_id', None)
            return jsonify(error='Tu sesión venció. Vuelve a ingresar.'), 401
        # Clave inicial o vencida: solo se permite crear la nueva.
        if session.get('form_debe_cambiar') and request.endpoint != 'form_pruebas.cambiar_clave':
            return jsonify(error='Debes cambiar tu clave para continuar.', codigo='CAMBIAR_CLAVE'), 403
        g.tecnico = person
        return fn(*args, **kwargs)
    return wrapped


@bp.get('/')
def inicio():
    csrf()
    return render_template('form_pruebas.html', autenticado=bool(session.get('form_documento')),
                           debe_cambiar=bool(session.get('form_debe_cambiar')),
                           catalogo_gastos=CATALOGO_GASTOS,
                           bancos=BANCOS)


@bp.get('/ruc/<numero>')
@tecnico
def ruc_emisor(numero):
    if not re.fullmatch(r'[0-9]{11}', numero):
        return jsonify(error='Ingresa un RUC de 11 dígitos.'), 400
    resultado = jsonify(piloto.consultar_ruc(numero))
    resultado.headers['Cache-Control'] = 'no-store'
    return resultado


@bp.post('/ingresar')
def ingresar():
    data = request.get_json(silent=True) or {}
    doc = piloto.documento(data.get('documento'))
    password = str(data.get('clave') or '')
    # Solo cuentan las claves erradas, por documento + IP: muchos técnicos entrando a la vez
    # (o compartiendo la IP del operador móvil) no se bloquean entre sí.
    key = hmac.new(str(current_app.secret_key).encode(),
                   f"{request.remote_addr or 'local'}|{doc}".encode(), 'sha256').hexdigest()
    now = time.time()
    with piloto.almacen() as con:
        previous = con.execute('SELECT cantidad,inicio FROM intentos WHERE clave=?', (key,)).fetchone()
    if previous and now - previous['inicio'] < 60 and previous['cantidad'] >= 8:
        return jsonify(error='Espera un minuto antes de volver a intentar.'), 429
    person = piloto.buscar_personal(doc) if re.fullmatch(r'[A-Z0-9]{6,15}', doc) else None
    if not person or not claves.verificar(doc, password):
        count = previous['cantidad'] + 1 if previous and now - previous['inicio'] < 60 else 1
        start = previous['inicio'] if previous and now - previous['inicio'] < 60 else now
        with piloto.almacen() as con:
            con.execute('INSERT OR REPLACE INTO intentos VALUES(?,?,?)', (key, count, start))
        return jsonify(error='Documento o clave incorrectos, o personal no habilitado. Consulta con tu supervisor.'), 401
    if previous:
        with piloto.almacen() as con:
            con.execute('DELETE FROM intentos WHERE clave=?', (key,))
    iniciar_tecnico(person)
    session['form_debe_cambiar'] = claves.debe_cambiar(doc)
    return jsonify(success=True, debe_cambiar=session['form_debe_cambiar'])


@bp.post('/clave')
@tecnico
def cambiar_clave():
    data = request.get_json(silent=True) or {}
    doc = g.tecnico['documento']
    actual, nueva, confirmar = (str(data.get(k) or '') for k in ('actual', 'nueva', 'confirmar'))
    error = claves.error_nueva(doc, actual, nueva, confirmar)
    if error:
        return jsonify(error=error), 400
    claves.cambiar(doc, nueva)
    session['form_debe_cambiar'] = False
    return jsonify(success=True)


@bp.post('/salir')
def salir():
    session.clear()
    return jsonify(success=True)


def responsables_por_proyecto():
    usuarios = (Usuario.query.with_entities(Usuario.id, Usuario.nombre, Proyecto.nombre.label('proyecto'))
                .join(AccesoProyecto, AccesoProyecto.usuario_id == Usuario.id)
                .join(Proyecto, Proyecto.id == AccesoProyecto.proyecto_id)
                .filter(Proyecto.nombre.in_(FLM_NOMBRES))
                .order_by(Usuario.nombre, Usuario.id))
    responsables = {proyecto: {} for proyecto in PROYECTOS}
    for uid, nombre, proyecto in usuarios:
        if nombre and nombre.strip():
            responsables[familia(proyecto)][str(uid)] = nombre.strip()
    return responsables


@bp.get('/datos')
@tecnico
def datos():
    documento = g.tecnico['documento']
    filas = piloto.filas_rendicion(documento)
    items = piloto.depositos(documento, filas)
    for item in items:
        for partida in item.get('partidas', []):
            categoria, detalle = partida['categoria'], partida['detalle']
            if partida.get('etiqueta'):
                continue
            if detalle:
                prefijo = {'COMPRAS': 'Compra', 'ALQUILER': 'Alquiler'}.get(categoria, categoria.capitalize())
                partida['etiqueta'] = f'{prefijo} de {detalle.lower()}'
            else:
                partida['etiqueta'] = ETIQUETAS_GASTO.get(categoria, categoria.capitalize())
    with piloto.almacen() as con:
        rows = con.execute('SELECT id,tipo,creado,datos FROM envios WHERE documento=? ORDER BY creado DESC LIMIT 8',
                           (g.tecnico['documento'],)).fetchall()
    recent = [{'id': r['id'], 'tipo': r['tipo'], 'creado': r['creado'],
               'monto': json.loads(r['datos'])['monto']} for r in rows]
    with piloto.almacen() as con:
        solicitudes = con.execute(
            "SELECT id, creado, datos FROM envios WHERE documento=? AND tipo='solicitud' ORDER BY creado DESC",
            (documento,)).fetchall()
    historial = []
    for solicitud in solicitudes:
        registro = json.loads(solicitud['datos'])
        historial.append({
            'codigo': piloto.codigo_solicitud(solicitud['id']),
            'estado': registro.get('estado', 'Pendiente'),
            'monto': registro['monto'], 'fecha_solicitud': piloto.fecha_solicitud(solicitud['creado']),
            'motivo': registro.get('motivo', ''), 'rechazo': registro.get('motivo_rechazo', ''),
            'foto': url_for('form_pruebas.foto_deposito_prueba', uid=solicitud['id'])
            if registro.get('foto_pago') else '', 'prueba': True,
        })
    for fila in filas:
        registro = json.loads(fila.data_json or '{}')
        estado = str(piloto.valor(registro, 'ESTADO')).strip().upper()
        etapa = piloto.etapa_de(registro)
        pagado = estado in ('DEPOSITADO', 'CON SUSTENTO', 'OBSERVADO', 'SUSTENTADO', 'ARCHIVADO')
        historial.append({
            'codigo': piloto.valor(registro, 'CODIGO DEPOSITO') or 'Sin código de depósito',
            'estado': 'Pagado' if pagado else 'Rechazado' if estado == 'RECHAZADO' else estado or 'Pendiente',
            'estado_rendicion': etapa.capitalize()
            if etapa in ('OBSERVADO', 'ARCHIVADO') else estado.capitalize() or 'Pendiente',
            'monto': str(piloto.valor(registro, 'Monto total del depósito', 'Monto total', 'Monto', 'MONTO PAGO')),
            'fecha_solicitud': piloto.fecha_solicitud(piloto.valor(registro, 'Marca temporal')),
            'motivo': str(piloto.valor(registro, 'Motivo de la solicitud')),
            'rechazo': str(piloto.valor(registro, 'MOTIVO RECHAZO')),
            'foto': url_for('form_pruebas.foto_deposito_real', registro=fila.id)
            if foto_pago_referencia(fila, registro) else '', 'prueba': False,
        })
    return jsonify(personal=g.tecnico, depositos=items,
                   total=str(sum((Decimal(d['pendiente']) for d in items), Decimal('0'))),
                   gastos=GASTOS, proyectos=PROYECTOS, proyecto_default=familia(g.tecnico['proyecto']),
                   responsables_validacion=responsables_por_proyecto(),
                   csrf=csrf(), recientes=recent, historial=historial)


def foto_pago_referencia(fila, datos):
    try:
        url = urlsplit(str(piloto.valor(datos, 'FOTO PAGO')))
    except ValueError:
        return None
    prefijo = f'/api/rendicion/foto/{fila.proyecto_id}/'
    ruta = unquote(url.path)
    if url.scheme or url.netloc or not ruta.startswith(prefijo):
        return None
    clave, _, nombre = ruta[len(prefijo):].rpartition('/')
    if (clave not in (fila.key_value, secure_filename(fila.key_value))
            or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)', nombre, re.IGNORECASE)):
        return None
    return nombre


@bp.get('/deposito/registro/<int:registro>/foto')
@tecnico
def foto_deposito_real(registro):
    filas = piloto.filas_rendicion(g.tecnico['documento'], registro)
    if not filas:
        abort(404)
    fila = filas[0]
    nombre = foto_pago_referencia(fila, json.loads(fila.data_json or '{}'))
    if not nombre:
        abort(404)
    from blueprints.rendicion import _servir_foto_rendicion
    return _servir_foto_rendicion(fila.proyecto_id, fila.key_value, nombre)


@bp.get('/deposito/prueba/<uid>/foto')
@tecnico
def foto_deposito_prueba(uid):
    if not re.fullmatch(r'[a-f0-9]{32}', uid):
        abort(404)
    with piloto.almacen() as con:
        fila = con.execute("SELECT datos FROM envios WHERE id=? AND documento=? AND tipo='solicitud'",
                           (uid, g.tecnico['documento'])).fetchone()
    if not fila or not json.loads(fila['datos']).get('foto_pago'):
        abort(404)
    return send_file(piloto.raiz() / 'pagos' / (uid + '.jpg'), mimetype='image/jpeg')


@bp.get('/sugerencias')
@tecnico
def sugerencias():
    proyecto = request.args.get('proyecto', '')
    campo = request.args.get('campo', '')
    consulta = request.args.get('q', '').strip()[:100]
    if proyecto not in PROYECTOS or campo not in ('site', 'wo'):
        return jsonify(error='Selecciona un proyecto válido.'), 400
    if len(consulta) < 2:
        return jsonify(opciones=[])
    from models import NucleusData, Proyecto
    from sqlalchemy import JSON, cast, func
    filas_proyecto = NucleusData.query.join(Proyecto, Proyecto.id == NucleusData.proyecto_id).filter(
        Proyecto.nombre == 'FLM - ' + proyecto)
    if campo == 'site':
        from services.cotizacion_ficha import sitios
        nombres = [item['site_name'] for item in sitios(consulta, proyecto=proyecto) if item['site_name']]
        if len(set(nombres)) < 15:
            datos = NucleusData.data_json
            claves = ('Site Name', 'Site Id Name', 'Nombre de Site', 'NOMBRE DE SITE', 'NOMBRE SITE')
            if piloto.db.engine.dialect.name == 'sqlite':
                campos = [func.json_extract(datos, '$."' + clave + '"') for clave in claves]
            else:
                campos = [cast(datos, JSON)[clave].as_string() for clave in claves]
            nombre = func.coalesce(*(func.nullif(campo, '') for campo in campos))
            coincidencias = (filas_proyecto.with_entities(nombre)
                             .filter(func.upper(nombre).contains(consulta.upper(), autoescape=True))
                             .distinct().order_by(nombre).limit(15).all())
            nombres.extend(fila[0] for fila in coincidencias)
        return jsonify(opciones=list(dict.fromkeys(nombres))[:15])
    filas = (filas_proyecto.with_entities(NucleusData.key_value)
             .filter(func.upper(NucleusData.key_value).contains(consulta.upper(), autoescape=True))
             .distinct().order_by(NucleusData.key_value).limit(15).all())
    return jsonify(opciones=[fila.key_value for fila in filas])


def texto(data, key, title, maximum, required=True):
    result = str(data.get(key) or '').strip()
    if (required and not result) or len(result) > maximum:
        raise ValueError(f'Completa {title} (máximo {maximum} caracteres).')
    return result


def nonce(data):
    result = str(data.get('nonce') or '')
    if not re.fullmatch(r'[a-f0-9]{32}', result):
        raise ValueError('Actualiza la página antes de enviar el formulario.')
    return result


def repetido(doc, key, tipo):
    previous = piloto.existente(doc, key)
    if previous:
        if previous['tipo'] != tipo:
            abort(409, 'El envío ya se utilizó. Actualiza la página.')
        datos = json.loads(previous['datos'])
        return jsonify(success=True, id=previous['id'], repetido=True,
                       codigo=piloto.codigo_solicitud(previous['id']) if tipo == 'solicitud' else None,
                       monto=datos['monto'], fotos_comprobante_repetidas=datos.get('fotos_comprobante_repetidas', 0))


def importe_solicitud(valor):
    monto = str(valor).strip()
    if not re.fullmatch(r'[0-9]{1,6}(?:[.,][0-9]{1,2})?', monto):
        raise ValueError('Ingresa el monto en soles usando números y hasta dos decimales.')
    return piloto.importe(monto)


@bp.post('/solicitar')
@tecnico
def solicitar():
    data = request.get_json(silent=True) or {}
    try:
        key = nonce(data)
        previous = repetido(g.tecnico['documento'], key, 'solicitud')
        if previous:
            return previous
        gastos = data.get('tipo_gasto')
        if isinstance(gastos, str):
            gastos = [gastos.strip()]
        if not isinstance(gastos, list) or not gastos or len(gastos) > len(GASTOS) or any(
            not isinstance(gasto, str) or gasto not in (*GASTOS, 'MATERIAL') for gasto in gastos
        ):
            raise ValueError('Selecciona al menos un tipo de gasto de la lista.')
        gastos = ['MATERIALES' if gasto == 'MATERIAL' else gasto for gasto in gastos]
        kind = ', '.join(dict.fromkeys(gastos))
        proyecto = data.get('proyecto', familia(g.tecnico['proyecto']))
        if proyecto not in PROYECTOS:
            raise ValueError('Selecciona un proyecto válido.')
        detalles = {}
        for categoria, opciones in DETALLES_GASTO.items():
            elegidos = data.get('detalle_' + categoria.lower(), [])
            if (not isinstance(elegidos, list) or len(elegidos) > len(opciones)
                    or any(opcion not in opciones for opcion in elegidos)
                    or (elegidos and categoria not in gastos)):
                raise ValueError('Revisa el desglose de ' + categoria.lower() + '.')
            if elegidos:
                detalles[categoria] = list(dict.fromkeys(elegidos))
        datos_bancarios = {}
        if 'proyecto' in data or 'partidas' in data:
            payment = 'Transferencia bancaria'
            account = texto(data, 'cuenta_cci', 'el CCI', 20)
            if not re.fullmatch(r'[0-9]{20}', account):
                raise ValueError('Ingresa un CCI de 20 dígitos.')
            billetera = data.get('tipo_billetera', 'No aplica')
            if billetera not in ('No aplica', 'Yape', 'Plin'):
                raise ValueError('Selecciona un tipo de billetera válido.')
            numero = ''
            if billetera != 'No aplica':
                numero = texto(data, 'numero_billetera', 'el número de Yape o Plin', 9)
                if not re.fullmatch(r'[0-9]{9}', numero):
                    raise ValueError('El número de Yape o Plin debe tener 9 dígitos.')
            banco = data.get('banco')
            if banco not in BANCOS:
                raise ValueError('Selecciona un banco de la lista.')
            datos_bancarios = {
                'cuenta_cci': account, 'banco': banco,
                'titular': texto(data, 'titular', 'el titular de la cuenta', 150),
                'tipo_billetera': billetera, 'numero_billetera': numero,
            }
        else:
            payment = texto(data, 'medio_pago', 'el medio de pago', 30)
            if payment not in ('Yape', 'Plin', 'Transferencia bancaria', 'No aplica'):
                raise ValueError('Selecciona un medio de pago válido.')
            account = '' if payment == 'No aplica' else texto(data, 'cuenta', 'el número de cuenta o celular', 20)
            if payment == 'Transferencia bancaria':
                if not re.fullmatch(r'[0-9]{20}', account):
                    raise ValueError('Ingresa un CCI de 20 dígitos.')
                datos_bancarios['banco'] = texto(data, 'banco', 'el nombre del banco', 100)
            if payment != 'No aplica' and not re.fullmatch(r'[0-9]{9,20}', account):
                raise ValueError('El celular, cuenta o CCI debe tener entre 9 y 20 dígitos.')
        partidas = []
        clasificaciones = set()
        esperadas = [(gasto, detalle) for gasto in dict.fromkeys(gastos)
                     for detalle in detalles.get(gasto, [''])]
        reglas = {}
        for concepto in esperadas:
            if concepto not in REGLAS_GASTO:
                raise ValueError('Selecciona una opción específica para cada tipo de gasto.')
            etiqueta, regla = REGLAS_GASTO[concepto]
            presupuesto = regla.get(proyecto) if isinstance(regla, dict) else regla
            if not presupuesto:
                raise ValueError(f'{etiqueta} no está disponible para {proyecto}.')
            reglas[concepto] = (etiqueta, presupuesto)
            clasificaciones.add(presupuesto)
        if 'partidas' in data:
            recibidas = data['partidas']
            if not isinstance(recibidas, list) or len(recibidas) != len(esperadas):
                raise ValueError('Ingresa el monto de cada gasto seleccionado.')
            amount = Decimal('0.00')
            for partida in recibidas:
                if not isinstance(partida, dict):
                    raise ValueError('Los importes deben corresponder a los gastos seleccionados.')
                categoria, detalle = partida.get('categoria'), partida.get('detalle')
                if not isinstance(categoria, str) or not isinstance(detalle, str) or (categoria, detalle) not in reglas:
                    raise ValueError('Los importes deben corresponder a los gastos seleccionados.')
                etiqueta, presupuesto = reglas.pop((categoria, detalle))
                importe = importe_solicitud(partida.get('monto'))
                amount += importe
                partidas.append({'categoria': categoria, 'detalle': detalle, 'monto': str(importe),
                                 'etiqueta': etiqueta, 'presupuesto': presupuesto})
            piloto.importe(amount)
        else:
            amount = importe_solicitud(data.get('monto'))
        motivo = texto(data, 'motivo', 'el motivo', 1000, required=not partidas)
        comentarios = texto(data, 'comentarios', 'la justificación de la solicitud', 1000, False)
        if not motivo:
            motivo = ', '.join(partida['etiqueta'] for partida in partidas)
        payload = {'monto': str(amount), 'tipo_gasto': kind, 'detalle_gasto': detalles,
                   'partidas': partidas, 'proyecto': proyecto,
                   'presupuesto': next(iter(clasificaciones)) if len(clasificaciones) == 1 else 'Mixto',
                   'motivo': motivo,
                   'wo': texto(data, 'wo', 'la WO', 200, False),
                   'site': texto(data, 'site', 'el site', 200, False),
                   'medio_pago': payment, 'cuenta': account,
                   'personal': g.tecnico, **datos_bancarios}
        if 'proyecto' in data:
            responsable_id = texto(data, 'responsable_validacion', 'el responsable de la validación', 10, False)
            responsable = ''
            if responsable_id:
                responsable = responsables_por_proyecto()[proyecto].get(responsable_id)
                if not responsable:
                    raise ValueError('Selecciona un responsable asignado al proyecto de la solicitud.')
                payload['responsable_validacion_id'] = int(responsable_id)
            payload.update(
                dni=g.tecnico['documento'],
                responsable_validacion=responsable,
                comentarios=comentarios)
        uid, creado = piloto.guardar(g.tecnico['documento'], 'solicitud', payload, key, uuid.uuid4().hex)
        if not creado:
            return repetido(g.tecnico['documento'], key, 'solicitud')
        return jsonify(success=True, id=uid, codigo=piloto.codigo_solicitud(uid), monto=payload['monto']), 201
    except ValueError as error:
        return jsonify(error=str(error)), 400


def preparar_fotos(files):
    if not 1 <= len(files) <= 8:
        raise ValueError('Agrega entre 1 y 8 fotos de tus comprobantes.')
    converted = []
    for file in files:
        raw = file.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('Cada foto debe pesar como máximo 10 MB.')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > 25_000_000:
                    raise ValueError('La foto es demasiado grande. Reduce su resolución.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1600, 1600))
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=82, optimize=True)
                converted.append(output.getvalue())
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValueError('Una foto no se pudo abrir. Usa JPG, PNG o WebP.') from None
    return converted


def comprobantes_rendicion(deposit):
    conceptos = deposit.get('partidas') or [{'concepto': deposit['motivo'] or 'Gasto del depósito'}]
    grupos = json.loads(request.form.get('comprobantes', 'null'))
    if not isinstance(grupos, list) or len(grupos) != len(conceptos):
        raise ValueError('La rendición debe incluir todos los conceptos de la solicitud.')
    partidas = []
    fotos = []
    for indice, (concepto, grupo) in enumerate(zip(conceptos, grupos)):
        if not isinstance(grupo, list) or len(grupo) > 8:
            raise ValueError('Puedes agregar hasta 8 comprobantes por concepto.')
        comprobantes = []
        for posicion, datos in enumerate(grupo):
            if not isinstance(datos, dict) or datos.get('tipo') not in ('Boleta', 'Factura'):
                raise ValueError('Selecciona Boleta o Factura para cada comprobante.')
            ruc = texto(datos, 'ruc', 'el RUC del emisor', 11, required=datos['tipo'] == 'Factura')
            if ruc and not re.fullmatch(r'[0-9]{11}', ruc):
                raise ValueError('El RUC debe tener 11 dígitos.')
            foto = request.files.get(f'comprobante-{indice}-{posicion}')
            if foto is None or not foto.filename:
                raise ValueError('Adjunta una foto para cada comprobante.')
            fotos.append(foto)
            comprobantes.append({'tipo': datos['tipo'], 'ruc': ruc,
                                 'monto': str(importe_solicitud(datos.get('monto')))})
        gastado = sum((Decimal(c['monto']) for c in comprobantes), Decimal('0.00'))
        partidas.append({**concepto, 'gastado': str(gastado), 'comprobantes': comprobantes})
    if len(fotos) > 24:
        raise ValueError('Puedes adjuntar hasta 24 comprobantes por rendición.')
    return partidas, fotos


@bp.post('/rendir')
@tecnico
def rendir():
    written = []
    try:
        key = nonce(request.form)
        previous = repetido(g.tecnico['documento'], key, 'rendicion')
        if previous:
            return previous
        ref = str(request.form.get('referencia') or '')
        deposit = next((d for d in piloto.depositos(g.tecnico['documento']) if d['referencia'] == ref), None)
        if deposit is None:
            abort(403, 'Este depósito no está disponible para tu documento.')
        saldo = Decimal(deposit['pendiente'])
        if saldo <= 0:
            raise ValueError('Este depósito ya no tiene saldo por rendir.')
        partidas, archivos = comprobantes_rendicion(deposit)
        gastado = sum((Decimal(p['gastado']) for p in partidas), Decimal('0.00'))
        if gastado > saldo:
            raise ValueError('El total de los comprobantes supera el saldo por rendir.')
        diferencia = saldo - gastado
        devolucion = None
        foto_devolucion = request.files.get('foto_devolucion')
        if diferencia:
            if not request.form.get('monto_devolucion'):
                raise ValueError(f'Registra una devolución de S/ {diferencia:.2f} para completar el saldo.')
            devuelto = importe_solicitud(request.form['monto_devolucion'])
            if devuelto != diferencia:
                raise ValueError(f'La devolución debe ser exactamente S/ {diferencia:.2f}.')
            motivo = texto(request.form, 'motivo_devolucion', 'el motivo de la devolución', 1000)
            if not foto_devolucion or not foto_devolucion.filename:
                raise ValueError('Adjunta la foto del comprobante de devolución.')
            devolucion = {'monto': str(devuelto), 'motivo': motivo}
        elif request.form.get('monto_devolucion') or foto_devolucion:
            raise ValueError('Los comprobantes cubren el saldo completo. Envía sin devolución.')

        images = [preparar_fotos([archivo])[0] for archivo in archivos]
        huellas = [hashlib.sha256(image).hexdigest() for image in images]
        evidencias_vinculadas = []
        if request.form.get('evidencia_por_comprobante') == '1':
            for indice, partida in enumerate(partidas):
                for posicion, comprobante in enumerate(partida['comprobantes']):
                    archivo = request.files.get(f'evidencia-{indice}-{posicion}')
                    if not archivo or not archivo.filename:
                        raise ValueError('Adjunta una evidencia del gasto junto a cada comprobante.')
                    evidencias_vinculadas.append(comprobante)
                    images.extend(preparar_fotos([archivo]))
        fotos_evidencia = [f for f in request.files.getlist('evidencia') if f.filename]
        if fotos_evidencia:
            images.extend(preparar_fotos(fotos_evidencia))
        if devolucion:
            images.extend(preparar_fotos([foto_devolucion]))
        uid = uuid.uuid4().hex
        folder = piloto.raiz() / 'fotos'
        folder.mkdir(parents=True, exist_ok=True)
        names = []
        for image in images:
            name = uuid.uuid4().hex + '.jpg'
            path = folder / name
            path.write_bytes(image)
            written.append(path)
            names.append(name)
        nombres = iter(names)
        for partida in partidas:
            for comprobante in partida['comprobantes']:
                comprobante['foto'] = next(nombres)
        for comprobante in evidencias_vinculadas:
            comprobante['evidencia'] = next(nombres)
        evidencia = [comprobante['evidencia'] for comprobante in evidencias_vinculadas] + list(nombres)
        if devolucion:
            devolucion['foto'] = evidencia.pop()
        payload = {'referencia': ref, 'codigo': deposit['codigo'], 'monto': str(saldo),
                   'gastado': str(gastado), 'devolucion': devolucion, 'detalle': deposit['motivo'],
                   'fotos': names, 'personal': g.tecnico, 'partidas': partidas, 'evidencia': evidencia}
        result, created = piloto.guardar(g.tecnico['documento'], 'rendicion', payload, key,
                                        uid, saldo=Decimal(deposit['monto']), huellas=huellas)
        if not created:
            for path in written:
                path.unlink(missing_ok=True)
            return repetido(g.tecnico['documento'], key, 'rendicion')
        return jsonify(success=True, id=result,
                       fotos_comprobante_repetidas=payload.get('fotos_comprobante_repetidas', 0)), 201
    except Exception as error:
        for path in written:
            path.unlink(missing_ok=True)
        if isinstance(error, ValueError):
            return jsonify(error=str(error)), 400
        raise


@bp.get('/foto/<name>')
@tecnico
def foto(name):
    if not re.fullmatch(r'[a-f0-9]{32}\.jpg', name):
        abort(404)
    with piloto.almacen() as con:
        rows = con.execute("SELECT datos FROM envios WHERE documento=? AND tipo='rendicion'", (g.tecnico['documento'],)).fetchall()
    if not any(name in json.loads(r['datos']).get('fotos', []) for r in rows):
        abort(404)
    return send_file(piloto.raiz() / 'fotos' / name, mimetype='image/jpeg')


@bp.get('/administrar/rendicion/<uid>/foto/<name>')
@login_required
def foto_revision(uid, name):
    if str(session.get('rol') or '').lower() not in ROLES_ADMIN_PILOTO:
        abort(403)
    if not re.fullmatch(r'[a-f0-9]{32}\.jpg', name):
        abort(404)
    with piloto.almacen() as con:
        fila = con.execute("SELECT datos FROM envios WHERE id=? AND tipo='rendicion'", (uid,)).fetchone()
    ruta = piloto.raiz() / 'fotos' / name
    if not fila or name not in json.loads(fila['datos']).get('fotos', []) or not ruta.is_file():
        abort(404)
    return send_file(ruta, mimetype='image/jpeg')


ACCIONES_SOLICITUD = {
    'aprobar': ('Pendiente', 'Aprobado'),
    'rechazar': ('Pendiente', 'Rechazado'),
    'pagar': ('Aprobado', 'Pagado'),
}


def alcance_gestion(bandeja):
    rol = str(session.get('rol') or '').lower()
    if rol in ROLES_ADMIN_PILOTO:
        return None
    if bandeja not in ('validacion', 'por-rendir') or rol not in ('gestor', 'supervisor'):
        abort(403)
    from services.utilidades import get_menu_proyectos
    return {familia(p.nombre) for p in get_menu_proyectos(session['user_id'], rol)} - {''}


def solicitud_en_alcance(datos, alcance):
    return alcance is None or familia(datos.get('proyecto') or datos.get('personal', {}).get('proyecto')) in alcance


def resolver_solicitud(accion, alcance):
    uid = request.form.get('id', '')
    if not re.fullmatch(r'[a-f0-9]{32}', uid):
        abort(404)
    esperado, nuevo = ACCIONES_SOLICITUD[accion]
    ruta_pago = None
    try:
        with piloto.almacen() as con:
            con.execute('BEGIN IMMEDIATE')
            fila = con.execute("SELECT datos FROM envios WHERE id=? AND tipo='solicitud'", (uid,)).fetchone()
            if not fila:
                abort(404)
            datos = json.loads(fila['datos'])
            if not solicitud_en_alcance(datos, alcance):
                abort(403)
            if datos.get('estado', 'Pendiente') != esperado:
                abort(409, 'La solicitud ya cambió de estado. Actualiza la bandeja.')
            ahora = datetime.now(timezone.utc).isoformat()
            datos.update(estado=nuevo, fecha_estado=ahora)
            if accion == 'rechazar':
                datos['motivo_rechazo'] = texto(request.form, 'motivo', 'el motivo del rechazo', 500)
            if accion == 'pagar':
                archivo = request.files.get('comprobante')
                imagen = preparar_fotos([archivo] if archivo and archivo.filename else [])[0]
                carpeta = piloto.raiz() / 'pagos'
                carpeta.mkdir(exist_ok=True)
                ruta_pago = carpeta / (uid + '.jpg')
                ruta_pago.write_bytes(imagen)
                datos['foto_pago'] = True
            datos.setdefault('historial_gestion', []).append({
                'accion': accion, 'usuario_id': session['user_id'], 'fecha': ahora,
            })
            con.execute('UPDATE envios SET datos=? WHERE id=?', (json.dumps(datos, ensure_ascii=False), uid))
    except Exception:
        if ruta_pago is not None:
            ruta_pago.unlink(missing_ok=True)
        raise


@bp.route('/gestion/<bandeja>', methods=['GET', 'POST'])
@login_required
def gestion(bandeja):
    if bandeja not in ('validacion', 'depositos', 'por-rendir'):
        abort(404)
    alcance = alcance_gestion(bandeja)
    if bandeja == 'por-rendir':
        if request.method != 'GET':
            abort(405)
        return render_template('form_pruebas_gestion.html', bandeja=bandeja,
                               tecnicos=piloto.pendientes_por_tecnico(alcance),
                               puede_depositar=alcance is None)
    validacion = bandeja == 'validacion'
    error = ''
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion not in (('aprobar', 'rechazar') if validacion else ('pagar',)):
            abort(403)
        try:
            resolver_solicitud(accion, alcance)
        except ValueError as exc:
            error = str(exc)
        else:
            return redirect(url_for('form_pruebas.gestion', bandeja=bandeja, registrado=accion))
    estado = 'Pendiente' if validacion else 'Aprobado'
    with piloto.almacen() as con:
        rows = con.execute("SELECT id, creado, datos FROM envios WHERE tipo='solicitud' ORDER BY creado DESC")
        envios = []
        for fila in rows:
            datos = json.loads(fila['datos'])
            if datos.get('estado', 'Pendiente') == estado and solicitud_en_alcance(datos, alcance):
                envios.append({'id': fila['id'], 'datos': datos,
                               'codigo': piloto.codigo_solicitud(fila['id']),
                               'fecha': piloto.fecha_solicitud(fila['creado'])})
    return render_template('form_pruebas_gestion.html', bandeja=bandeja, envios=envios, validacion=validacion,
                           puede_depositar=alcance is None, csrf_token=csrf(), error=error,
                           registrado=request.args.get('registrado') in ACCIONES_SOLICITUD), 400 if error else 200


@bp.route('/administrar', methods=['GET', 'POST'])
@login_required
def administrar():
    if str(session.get('rol') or '').lower() not in ROLES_ADMIN_PILOTO:
        abort(403)
    if request.method == 'POST':
        comprobar_csrf()
        folder = piloto.raiz()
        folder.mkdir(parents=True, exist_ok=True)
        accion = request.form.get('accion')
        if accion == 'habilitar':
            (folder / 'habilitado').touch()
        elif accion == 'deshabilitar':
            (folder / 'habilitado').unlink(missing_ok=True)
        elif accion == 'reglas':
            from services import caja_chica_reglas as reglas
            datos = {n: {'activa': request.form.get(n + '_activa') == '1', 'valor': request.form.get(n + '_valor', ''),
                         'proyectos': request.form.getlist(n + '_proyectos')} for n in reglas.REGLAS}
            from services import audit_user
            try:
                reglas.guardar(datos, audit_user() or 'admin')
            except ValueError as error:
                return redirect(url_for('form_pruebas.administrar', error=str(error)) + '#restricciones')
            return redirect(url_for('form_pruebas.administrar', guardado=1) + '#restricciones')
        elif accion in ACCIONES_SOLICITUD:
            try:
                resolver_solicitud(accion, None)
            except ValueError as error:
                abort(400, str(error))
        else:
            abort(400)
        return redirect(url_for('form_pruebas.administrar'))
    csrf()
    with piloto.almacen() as con:
        rows = con.execute('SELECT id,tipo,creado,documento,datos FROM envios ORDER BY creado DESC LIMIT 100').fetchall()
    entries = [{**dict(r), 'datos': json.loads(r['datos'])} for r in rows]
    from services import caja_chica_reglas as reglas
    return render_template('form_pruebas_admin.html', envios=entries, habilitado=habilitado(),
                           reglas=reglas.leer(), definicion=reglas.REGLAS, proyectos_reglas=reglas.PROYECTOS)
