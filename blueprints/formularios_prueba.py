"""Dos formularios móviles en paralelo al flujo real de Google Forms."""
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
from services.rendicion_gastos import OPCIONES
from services.recursos_flm import FLM_NOMBRES, familia

bp = Blueprint('form_pruebas', __name__, url_prefix='/form-pruebas')
PROYECTOS = ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT')
GASTOS_ADICIONALES = (
    'FLETE Y ENVÍOS', 'GRÚA Y REMOLQUE', 'MANTENIMIENTO VEHICULAR',
    'REPARACIÓN DE EQUIPOS', 'SERVICIOS DE TERCEROS', 'ACCESOS Y PERMISOS', 'COMUNICACIONES',
)
GASTOS = tuple('MATERIALES' if opcion == 'MATERIAL' else opcion
               for opcion in OPCIONES if opcion not in ('OTROS', 'HOSPEDAJE')) + GASTOS_ADICIONALES
ETIQUETAS_GASTO = {
    'PASAJE': 'Pasajes',
    'MATERIAL': 'Compra de materiales',
    'MATERIALES': 'Compra de materiales',
    'VIATICOS': 'Viáticos',
}
DETALLES_GASTO = {
    'COMPRAS': ('Consumibles', 'Equipos y accesorios'),
    'ALQUILER': ('Vehículos', 'Herramientas', 'Equipos', 'Generadores'),
}
PRESUPUESTOS = ('Gasto Cobra', 'Refacturable')
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
        g.tecnico = person
        return fn(*args, **kwargs)
    return wrapped


@bp.get('/')
def inicio():
    csrf()
    return render_template('form_pruebas.html', autenticado=bool(session.get('form_documento')),
                           gastos=GASTOS, detalles_gasto=DETALLES_GASTO, etiquetas_gasto=ETIQUETAS_GASTO,
                           bancos=BANCOS)


@bp.post('/ingresar')
def ingresar():
    data = request.get_json(silent=True) or {}
    doc = piloto.documento(data.get('documento'))
    password = str(data.get('clave') or '')
    key = hmac.new(str(current_app.secret_key).encode(),
                   (request.remote_addr or 'local').encode(), 'sha256').hexdigest()
    with piloto.almacen() as con:
        previous = con.execute('SELECT cantidad,inicio FROM intentos WHERE clave=?', (key,)).fetchone()
        now = time.time()
        if previous and now - previous['inicio'] < 60 and previous['cantidad'] >= 8:
            return jsonify(error='Espera un minuto antes de volver a intentar.'), 429
        count = previous['cantidad'] + 1 if previous and now - previous['inicio'] < 60 else 1
        start = previous['inicio'] if previous and now - previous['inicio'] < 60 else now
        con.execute('INSERT OR REPLACE INTO intentos VALUES(?,?,?)', (key, count, start))
    person = piloto.buscar_personal(doc) if re.fullmatch(r'[A-Z0-9]{6,15}', doc) else None
    if not person or not hmac.compare_digest(doc, password):
        return jsonify(error='Documento o clave incorrectos, o personal no habilitado. Consulta con tu supervisor.'), 401
    iniciar_tecnico(person)
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
             .filter(func.upper(NucleusData.key_value).contains(consulta.upper(), autoescape=True),
                     NucleusData.key_value.like('CM-%') | NucleusData.key_value.like('PM-%')
                     | NucleusData.key_value.like('PLM-%'))
             .order_by(NucleusData.key_value).limit(15).all())
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
        return jsonify(success=True, id=previous['id'], repetido=True,
                       codigo=piloto.codigo_solicitud(previous['id']) if tipo == 'solicitud' else None,
                       monto=json.loads(previous['datos'])['monto'])


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
        kind = ', '.join(dict.fromkeys(gastos))
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
        if 'partidas' in data:
            esperadas = [(gasto, detalle) for gasto in dict.fromkeys(gastos)
                         for detalle in detalles.get(gasto, [''])]
            recibidas = data['partidas']
            if not isinstance(recibidas, list) or len(recibidas) != len(esperadas):
                raise ValueError('Ingresa el monto de cada gasto seleccionado.')
            amount = Decimal('0.00')
            for (categoria, detalle), partida in zip(esperadas, recibidas):
                if not isinstance(partida, dict) or (partida.get('categoria'), partida.get('detalle')) != (categoria, detalle):
                    raise ValueError('Los importes deben corresponder a los gastos seleccionados.')
                importe = importe_solicitud(partida.get('monto'))
                amount += importe
                partidas.append({'categoria': categoria, 'detalle': detalle, 'monto': str(importe)})
            piloto.importe(amount)
        else:
            amount = importe_solicitud(data.get('monto'))
        motivo = texto(data, 'motivo', 'el motivo', 1000, required=not partidas)
        comentarios = texto(data, 'comentarios', 'la justificación de la solicitud', 1000, False)
        if not motivo:
            motivo = ', '.join(
                f"{partida['categoria'].capitalize()}: {partida['detalle']}"
                if partida['detalle'] else ETIQUETAS_GASTO.get(partida['categoria'], partida['categoria'].capitalize())
                for partida in partidas
            )
        payload = {'monto': str(amount), 'tipo_gasto': kind, 'detalle_gasto': detalles,
                   'partidas': partidas,
                   'motivo': motivo,
                   'wo': texto(data, 'wo', 'la WO', 200, False),
                   'site': texto(data, 'site', 'el site', 200, False),
                   'medio_pago': payment, 'cuenta': account,
                   'personal': g.tecnico, **datos_bancarios}
        if 'proyecto' in data:
            proyecto = texto(data, 'proyecto', 'el proyecto', 20)
            presupuesto = texto(data, 'presupuesto', 'el tipo de presupuesto', 30)
            if proyecto not in PROYECTOS or presupuesto not in PRESUPUESTOS:
                raise ValueError('Selecciona un proyecto y un tipo de presupuesto válidos.')
            responsable_id = texto(data, 'responsable_validacion', 'el responsable de la validación', 10, False)
            responsable = ''
            if responsable_id:
                responsable = responsables_por_proyecto()[proyecto].get(responsable_id)
                if not responsable:
                    raise ValueError('Selecciona un responsable asignado al proyecto de la solicitud.')
                payload['responsable_validacion_id'] = int(responsable_id)
            payload.update(
                proyecto=proyecto, presupuesto=presupuesto, dni=g.tecnico['documento'],
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
        evidencia = list(nombres)
        if devolucion:
            devolucion['foto'] = evidencia.pop()
        payload = {'referencia': ref, 'codigo': deposit['codigo'], 'monto': str(saldo),
                   'gastado': str(gastado), 'devolucion': devolucion, 'detalle': deposit['motivo'],
                   'fotos': names, 'personal': g.tecnico, 'partidas': partidas, 'evidencia': evidencia}
        result, created = piloto.guardar(g.tecnico['documento'], 'rendicion', payload, key,
                                        uid, saldo=Decimal(deposit['monto']))
        if not created:
            for path in written:
                path.unlink(missing_ok=True)
        return jsonify(success=True, id=result), 201 if created else 200
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


@bp.route('/administrar', methods=['GET', 'POST'])
@login_required
def administrar():
    if str(session.get('rol') or '').lower() not in ('zeno', 'suport', 'admin'):
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
        elif accion in ('pagar', 'rechazar'):
            uid = request.form.get('id', '')
            if not re.fullmatch(r'[a-f0-9]{32}', uid):
                abort(404)
            try:
                if accion == 'pagar':
                    archivo = request.files.get('comprobante')
                    imagen = preparar_fotos([archivo] if archivo and archivo.filename else [])[0]
                    cambios = {'estado': 'Pagado', 'foto_pago': True}
                else:
                    cambios = {'estado': 'Rechazado',
                               'motivo_rechazo': texto(request.form, 'motivo', 'el motivo del rechazo', 500)}
            except ValueError as error:
                abort(400, str(error))
            with piloto.almacen() as con:
                con.execute('BEGIN IMMEDIATE')
                fila = con.execute("SELECT datos FROM envios WHERE id=? AND tipo='solicitud'", (uid,)).fetchone()
                if not fila:
                    abort(404)
                datos = json.loads(fila['datos'])
                if datos.get('estado', 'Pendiente') != 'Pendiente':
                    abort(409, 'La solicitud de prueba ya se resolvió.')
                if accion == 'pagar':
                    carpeta = folder / 'pagos'
                    carpeta.mkdir(exist_ok=True)
                    (carpeta / (uid + '.jpg')).write_bytes(imagen)
                datos.update(cambios, fecha_estado=datetime.now(timezone.utc).isoformat())
                con.execute('UPDATE envios SET datos=? WHERE id=?', (json.dumps(datos, ensure_ascii=False), uid))
        else:
            abort(400)
        return redirect(url_for('form_pruebas.administrar'))
    csrf()
    with piloto.almacen() as con:
        rows = con.execute('SELECT id,tipo,creado,documento,datos FROM envios ORDER BY creado DESC LIMIT 100').fetchall()
    entries = [{**dict(r), 'datos': json.loads(r['datos'])} for r in rows]
    return render_template('form_pruebas_admin.html', envios=entries, habilitado=habilitado())
