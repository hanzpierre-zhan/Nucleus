"""Solicitudes y evidencias de combustible en gestión y Nucleus Mobile."""
import io
import json
import re
from uuid import uuid4
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, send_file, session, url_for
from PIL import Image, ImageOps

from blueprints.formularios_prueba import comprobar_csrf, csrf, habilitado, tecnico
from db import db
from models import AbastecimientoFoto, AbastecimientoSolicitud as Solicitud, NucleusData, Proyecto
from services import get_menu_proyectos, login_required
from services.cotizacion_ficha import normalizar, sitios
from services.personal import DEPARTAMENTOS
from services.recursos_flm import familia
from services.utilidades import ahora_peru

bp = Blueprint('abastecimiento', __name__)
ESTADOS = {
    'gestora': 'Validación', 'parque': 'Generación QR', 'llenado': 'Abastecimiento',
    'recarga': 'Recarga', 'cerrado': 'Recarga completada',
}
ADMIN = ('zeno', 'admin', 'suport')
FOTOS_LLENADO = {'boleta': 'Boleta', 'antes_llenado': 'Antes del llenado', 'despues_llenado': 'Después del llenado'}
FOTOS_RECARGA = {'antes_recarga': 'Antes de la recarga en el site', 'despues_recarga': 'Después de la recarga en el site'}
FOTOS = {'qr': 'Código QR', **FOTOS_LLENADO, **FOTOS_RECARGA}
CERO = Decimal('0.00')
PROYECTOS_PRUEBA = ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT')
TIPOS_GENERADOR = ('PROPIO', 'ALQUILADO', 'CLIENTE', 'OTRO')
COMBUSTIBLES_GENERADOR = ('GASOLINA', 'PETRÓLEO', 'DIÉSEL', 'OTRO')
COMBUSTIBLES_PEDIDO = {'gasolina': 'Gasolina', 'petroleo': 'Petróleo', 'diesel': 'Diésel'}
GRIFOS_PEDIDO = {'primax': 'Primax', 'redcol': 'Redcol', 'otro': 'Otro'}
CAMPOS_GENERADOR = ('QR ASIGNADO', 'SERIE DE EQUIPO', 'ZONA', 'TIPO',
                    'TIPO DE COMBUSTIBLE', 'PROYECTO')


def cantidad(valor, etiqueta, minimo=CERO):
    try:
        n = Decimal(str(valor or '').strip().replace(',', '.'))
    except InvalidOperation:
        raise ValueError(f'Ingresa un valor válido para {etiqueta}.') from None
    if not n.is_finite() or not minimo <= n <= 9_999_999 or n.as_tuple().exponent < -2:
        raise ValueError(f'Revisa {etiqueta}. Se permiten hasta dos decimales.')
    return n


def referencias_pedido(form, anterior, cierre=False):
    datos = {}
    for campo, ejemplo in (('cm', 'CM-20261124-00000018'), ('plm', 'PLM-20261124-00000018')):
        valor_anterior = (anterior.get(campo) or '').strip().upper()
        valor = form.get(campo, valor_anterior).strip().upper()
        if cierre and not valor:
            raise ValueError(f'Completa {campo.upper()} para cerrar la recarga.')
        es_valido = re.fullmatch(fr'{campo.upper()}-[0-9]{{8}}-[0-9]{{8}}', valor)
        if valor and not es_valido and (cierre or valor != valor_anterior):
            raise ValueError(f'Ingresa {campo.upper()} con el formato {ejemplo}.')
        datos[campo] = valor
    return datos


def datos_pedido(form, proyecto, anterior=None, galones_anteriores=None, *, prueba=False):
    anterior = anterior or {}
    campos = 'fecha zona site codigo combustible otro_combustible placa generador'.split()
    datos = {campo: form.get(campo, '').strip()[:1000] for campo in campos}
    tipo = form.get('tipo')
    for campo, etiqueta in (('zona', 'zona de trabajo'), ('site', 'site')):
        if not datos[campo]:
            raise ValueError(f'Completa {etiqueta}.')
    datos.update(referencias_pedido(form, anterior))
    if 'grifo' in form:
        grifo = form.get('grifo', '').strip().lower()
        if grifo and grifo not in GRIFOS_PEDIDO:
            raise ValueError('Selecciona un grifo de la lista.')
        otro = form.get('grifo_otro', '').strip()[:150] if grifo == 'otro' else ''
        if grifo == 'otro' and not otro:
            raise ValueError('Escribe el nombre del otro grifo.')
        datos.update(grifo=GRIFOS_PEDIDO.get(grifo, ''), grifo_otro=otro)
    try:
        datos['fecha'] = date.fromisoformat(datos['fecha']).isoformat()
    except ValueError:
        raise ValueError('Selecciona la fecha del pedido.') from None
    combustible = datos['combustible']
    if combustible not in COMBUSTIBLES_PEDIDO and combustible != anterior.get('combustible'):
        raise ValueError('Selecciona el tipo de combustible.')
    if tipo not in ('vehiculo', 'generador'):
        raise ValueError('Selecciona vehículo o generador.')
    campo_unidad = 'placa' if tipo == 'vehiculo' else 'generador'
    unidad = re.sub(r'[^A-Z0-9]', '', datos[campo_unidad].upper())
    if not 1 <= len(unidad) <= 40:
        raise ValueError('Ingresa la placa o el identificador del generador.')
    if tipo == 'vehiculo':
        datos.update(generador='', generador_serie='')
    else:
        datos['placa'] = ''
        equipo = next((g for g in catalogo_generadores(proyecto, prueba=prueba) if g['qr'] == datos['generador']), None)
        if not equipo and datos['generador'] != anterior.get('generador'):
            raise ValueError('Selecciona un generador registrado en tu proyecto.')
        datos['generador_serie'] = equipo['serie'] if equipo else anterior.get('generador_serie', '')
    datos['tipo'] = tipo
    coincidencias = [s for s in catalogo_sites(proyecto, datos['site'])
                     if normalizar(datos['site']) in {normalizar(s['nombre']), normalizar(s['codigo']), normalizar(s['clave'])}]
    site = next((s for s in coincidencias if s['codigo'] == datos['codigo']), None)
    if site is None and len(coincidencias) == 1:
        site = coincidencias[0]
    datos['site_pendiente'] = site is None
    if site:
        datos.update(site=site['nombre'], codigo=site['codigo'])
    if combustible == 'petroleo':
        combustible = 'diesel'  # Comparte el saldo de la unidad con el diésel.
    if combustible == 'otro':
        combustible += ':' + re.sub(r'\s+', ' ', datos['otro_combustible'].casefold())[:34]
    galones = cantidad(form.get('galones'), 'galones solicitados', Decimal('0.01'))
    if galones != galones_anteriores and (galones < Decimal('0.1') or galones * 10 % 1):
        raise ValueError('Ingresa los galones solicitados con un máximo de un decimal, por ejemplo 1.1.')
    return datos, f'{tipo}:{unidad}:{combustible}', galones


def alcance():
    menu = get_menu_proyectos(session['user_id'], session['rol'])
    rol = session['rol']
    if rol not in (*ADMIN, 'gestor', 'supervisor') or not any(p.nombre == 'Abastecimiento' for p in menu):
        abort(403)
    return menu, rol, {familia(p.nombre) for p in menu if familia(p.nombre)}


def gestion():
    menu, rol, proyectos = alcance()
    pestañas = {k: v for k, v in ESTADOS.items() if k != 'cerrado'
                and (k != 'gestora' or rol != 'supervisor') and (k != 'parque' or rol != 'gestor')}
    pestañas['generadores'] = 'Generadores'
    estado = request.args.get('estado', next(iter(pestañas)))
    if estado == 'cerrado':
        return redirect(url_for('vistas_nuevas.abastecimiento', estado='recarga'))
    if estado not in pestañas:
        abort(404)
    if estado == 'generadores':
        filas = generadores_visibles(rol, proyectos)
        editar = request.args.get('editar', type=int)
        ficha = filas.get(editar)
        if editar is not None and ficha is None:
            abort(404)
        return render_template('abastecimiento.html', proyectos_list=menu, estado=estado, pestañas=pestañas,
                               csrf=csrf(), generadores=filas, ficha=ficha, editar=editar,
                               campos=CAMPOS_GENERADOR, tipos=TIPOS_GENERADOR, combustibles=COMBUSTIBLES_GENERADOR,
                               proyectos=PROYECTOS_PRUEBA if rol in ADMIN else sorted(proyectos))
    estados_visibles = ('recarga', 'cerrado') if estado == 'recarga' else (estado,)
    consulta = Solicitud.query.filter(Solicitud.estado.in_(estados_visibles))
    if rol not in ADMIN:
        consulta = consulta.filter(Solicitud.proyecto.in_(proyectos))
    filas = consulta.order_by(Solicitud.id.desc()).all()
    return render_template('abastecimiento.html', proyectos_list=menu, filas=filas, estado=estado,
                           pestañas=pestañas, fotos=FOTOS, csrf=csrf(), puede_probar=rol in ADMIN,
                           zonas=DEPARTAMENTOS, combustibles_pedido=COMBUSTIBLES_PEDIDO, grifos=GRIFOS_PEDIDO)


def bloquear_cambios():
    # Serializa altas y transiciones, incluso antes de que exista saldo para la unidad.
    db.session.execute(db.update(Proyecto).where(Proyecto.nombre == 'Abastecimiento')
                       .values(descripcion=Proyecto.descripcion))


def modulo_generadores():
    return Proyecto.query.filter_by(nombre='Generadores').first_or_404()


def fichas_generadores():
    for fila in NucleusData.query.filter_by(proyecto_id=modulo_generadores().id).order_by(NucleusData.id.desc()):
        try:
            datos = json.loads(fila.data_json)
        except ValueError:
            continue
        if isinstance(datos, dict):
            yield fila, datos


def generadores_visibles(rol, proyectos):
    return {fila.id: datos for fila, datos in fichas_generadores()
            if rol in ADMIN or familia(datos.get('PROYECTO') or datos.get('Proyecto')) in proyectos}


def catalogo_generadores(proyecto, *, prueba=False):
    resultado = {}
    for _, datos in fichas_generadores():
        asignado = datos.get('PROYECTO') or datos.get('Proyecto') or ''
        if familia(asignado) != proyecto and not (prueba and not str(asignado).strip()):
            continue
        qr = str(datos.get('QR ASIGNADO') or '').strip()
        if qr:
            resultado.setdefault(qr, {'qr': qr, 'serie': str(datos.get('SERIE DE EQUIPO') or '').strip(),
                                       'zona': str(datos.get('ZONA') or '').strip()})
    return sorted(resultado.values(), key=lambda g: g['qr'].casefold())


def catalogo_sites(proyecto, consulta):
    return [{'nombre': s['site_name'] or s['site_key'], 'codigo': s['site_id'],
             'clave': s['site_key']} for s in sitios(consulta, proyecto='ENTEL' if proyecto == 'PEXT' else proyecto)]


def datos_catalogo(proyecto, *, prueba=False):
    consulta = request.args.get('q', '').strip()[:120]
    tipo = request.args.get('ticket')
    if tipo is not None:
        if tipo not in ('CM', 'PLM'):
            abort(400)
        modulo = Proyecto.query.filter_by(nombre=f'FLM - {proyecto}').first()
        if not modulo:
            return jsonify(tickets=[])
        clave = NucleusData.key_value
        patron = re.compile(fr'{tipo}-[0-9]{{8}}-[0-9]{{8}}')
        filas = (db.session.query(clave)
                 .filter(NucleusData.proyecto_id == modulo.id,
                         clave.like(f'{tipo}-________-________'),
                         clave.icontains(consulta, autoescape=True))
                 .order_by(clave.desc()).limit(50))
        return jsonify(tickets=[codigo for (codigo,) in filas if patron.fullmatch(codigo)][:25])
    return jsonify(sites=catalogo_sites(proyecto, consulta),
                   generadores=[] if consulta else catalogo_generadores(proyecto, prueba=prueba))


@bp.get('/abastecimiento/catalogos')
@login_required
def catalogos_gestion():
    _, rol, proyectos = alcance()
    proyecto = request.args.get('proyecto')
    if proyecto not in (PROYECTOS_PRUEBA if rol in ADMIN else proyectos):
        abort(403)
    return datos_catalogo(proyecto, prueba=rol in ADMIN and request.args.get('prueba') == '1')


@bp.get('/form-pruebas/abastecimiento/catalogos')
@tecnico
def catalogos_tecnico():
    exigir_mobile()
    proyecto = familia(g.tecnico['proyecto'])
    if not proyecto:
        abort(403)
    return datos_catalogo(proyecto)


@bp.post('/abastecimiento/generadores/guardar')
@login_required
def guardar_generador():
    comprobar_csrf()
    _, rol, proyectos = alcance()
    bloquear_cambios()
    registro_id = request.form.get('registro', type=int)
    fichas = list(fichas_generadores())
    fila, anterior = next(((fila, datos) for fila, datos in fichas if fila.id == registro_id), (None, {}))
    if request.form.get('registro') and (fila is None or
            (rol not in ADMIN and familia(anterior.get('PROYECTO') or anterior.get('Proyecto')) not in proyectos)):
        abort(404)
    datos = {campo: request.form.get(campo, '').strip()[:150] for campo in CAMPOS_GENERADOR}
    datos['TIPO'] = datos['TIPO'].upper()
    combustible = datos['TIPO DE COMBUSTIBLE'].upper()
    datos['TIPO DE COMBUSTIBLE'] = {'PETROLEO': 'PETRÓLEO', 'DIESEL': 'DIÉSEL'}.get(combustible, combustible)
    if datos['TIPO DE COMBUSTIBLE'] and datos['TIPO DE COMBUSTIBLE'] not in COMBUSTIBLES_GENERADOR and combustible != str(anterior.get('TIPO DE COMBUSTIBLE') or '').upper():
        return error(ValueError('Selecciona un tipo de combustible.'))
    qr = datos['QR ASIGNADO']
    if not qr or not datos['SERIE DE EQUIPO'] or not datos['ZONA']:
        return error(ValueError('Completa el QR, la serie y la zona.'))
    if datos['TIPO'] not in TIPOS_GENERADOR and (not datos['TIPO'] or datos['TIPO'] != str(anterior.get('TIPO', '')).upper()):
        return error(ValueError('Selecciona el tipo de propiedad.'))
    seleccion = familia(datos['PROYECTO'])
    if seleccion not in (PROYECTOS_PRUEBA if rol in ADMIN else proyectos):
        return error(ValueError('Selecciona uno de tus proyectos autorizados.'))
    if qr.casefold() != str(anterior.get('QR ASIGNADO', '')).strip().casefold() and any(
            qr.casefold() == str(otra.get('QR ASIGNADO', '')).strip().casefold() for _, otra in fichas):
        return error(ValueError('Ese QR ya está asignado a un generador.'))
    datos['PROYECTO'] = f'FLM - {seleccion}'
    if fila is None:
        fila = NucleusData(proyecto_id=modulo_generadores().id, key_value='GEN-' + uuid4().hex)
        db.session.add(fila)
    fila.data_json = json.dumps({**anterior, **datos}, ensure_ascii=False)
    db.session.commit()
    return jsonify(ok=True, destino=url_for('vistas_nuevas.abastecimiento', estado='generadores'))


def unidad_libre(unidad, excluir=None):
    consulta = Solicitud.query.filter(Solicitud.unidad == unidad, Solicitud.estado != 'cerrado')
    if excluir is not None:
        consulta = consulta.filter(Solicitud.id != excluir)
    if consulta.first():
        raise ValueError('Ya hay un pedido abierto para esa unidad y combustible. Completa sus evidencias antes de pedir nuevamente.')


def ultimo_saldo(unidad):
    previo = Solicitud.query.filter_by(unidad=unidad, estado='cerrado').order_by(Solicitud.id.desc()).first()
    return previo.saldo_final if previo else CERO


def guardar_foto(sol, tipo):
    archivo = request.files.get(tipo)
    if not archivo:
        raise ValueError(f'Adjunta la imagen de {FOTOS[tipo]}.')
    contenido = archivo.read(8 * 1024 * 1024 + 1)
    if len(contenido) > 8 * 1024 * 1024:
        raise ValueError('Cada imagen puede pesar hasta 8 MB.')
    salida = io.BytesIO()
    try:
        with Image.open(io.BytesIO(contenido), formats=['JPEG', 'PNG', 'WEBP']) as imagen:
            if imagen.width * imagen.height > 24_000_000:
                raise ValueError()
            imagen = ImageOps.exif_transpose(imagen).convert('RGB')
            if tipo == 'qr':
                imagen.save(salida, 'PNG')
            else:
                imagen.thumbnail((1600, 1600))
                imagen.save(salida, 'JPEG', quality=84)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValueError(f'La imagen de {FOTOS[tipo]} no es válida o es demasiado grande.') from None
    db.session.add(AbastecimientoFoto(solicitud_id=sol.id, tipo=tipo, contenido=salida.getvalue(),
                                      mime='image/png' if tipo == 'qr' else 'image/jpeg'))


def error(exc):
    db.session.rollback()
    return jsonify(error=str(exc)), 400


@bp.before_request
def limitar_carga():
    if request.content_length and request.content_length > 26 * 1024 * 1024:
        abort(413)


@bp.post('/abastecimiento/<int:sid>/<accion>')
@login_required
def revisar(sid, accion):
    comprobar_csrf()
    _, rol, proyectos = alcance()
    bloquear_cambios()
    sol = db.get_or_404(Solicitud, sid)
    if rol not in ADMIN and sol.proyecto not in proyectos:
        abort(404)
    try:
        if accion in ('editar', 'validar') and rol != 'supervisor' and sol.estado == 'gestora':
            datos, unidad, galones = datos_pedido(request.form, sol.proyecto, sol.datos, sol.solicitado,
                                                  prueba=sol.tecnico_id < 0)
            if sol.tecnico_id < 0:
                unidad = 'prueba:' + unidad
            unidad_libre(unidad, sol.id)
            sol.datos = {**sol.datos, **datos}
            sol.unidad, sol.solicitado = unidad, galones
            if accion == 'validar':
                sol.saldo_previo = ultimo_saldo(unidad)
                sol.autorizado = max(CERO, galones - sol.saldo_previo)
                sol.gestora_id, sol.estado = session['user_id'], 'parque'
        elif accion == 'enviar' and rol != 'gestor' and sol.estado == 'parque':
            if sol.autorizado > 0:
                guardar_foto(sol, 'qr')
            sol.parque_id = session['user_id']
            if sol.autorizado == 0:
                sol.cargado = CERO
            sol.estado = 'llenado' if sol.autorizado > 0 else 'recarga'
        else:
            return error(ValueError('La acción no está disponible para este pedido. Actualiza la página.'))
        db.session.commit()
    except ValueError as exc:
        return error(exc)
    return jsonify(ok=True)


@bp.get('/form-pruebas/abastecimiento')
def entrada():
    exigir_mobile()
    if not session.get('form_documento') or session.get('form_debe_cambiar'):
        return redirect(url_for('form_pruebas.inicio'))
    return portal()


@tecnico
def portal():
    return pantalla_tecnico(g.tecnico)


def exigir_mobile():
    if not habilitado() or not current_app.config.get('ABASTECIMIENTO_MOBILE_ENABLED', False):
        abort(404)


def pantalla_tecnico(persona, prueba=False):
    seccion = request.args.get('seccion', '')
    ruta = 'abastecimiento.prueba_pedidos' if prueba else 'abastecimiento.entrada'
    pedidos = Solicitud.query.filter_by(tecnico_id=persona['id']).order_by(Solicitud.id.desc())
    filas = pedidos.all() if seccion == 'bandeja' else []
    ultimo = pedidos.first() if prueba and seccion == 'solicitar' else None
    datos = {'fecha': ahora_peru().date().isoformat(), 'zona': persona['departamento']}
    return render_template('abastecimiento_mobile.html', filas=filas, datos=datos, persona=persona,
                           prueba=prueba, proyectos_prueba=PROYECTOS_PRUEBA, estados=ESTADOS, csrf=csrf(),
                           seccion=seccion, ruta=ruta,
                           proyecto=(ultimo.proyecto if ultimo else 'CLARO') if prueba else familia(persona['proyecto']),
                           zonas=DEPARTAMENTOS, combustibles_pedido=COMBUSTIBLES_PEDIDO, grifos=GRIFOS_PEDIDO,
                           fotos_llenado=FOTOS_LLENADO, fotos_recarga=FOTOS_RECARGA)


@bp.post('/form-pruebas/abastecimiento/solicitar')
@tecnico
def solicitar():
    exigir_mobile()
    comprobar_csrf()
    return crear_pedido(g.tecnico)


def crear_pedido(persona, prueba=False):
    try:
        proyecto = request.form.get('proyecto') if prueba else familia(persona['proyecto'])
        if prueba and proyecto not in PROYECTOS_PRUEBA:
            raise ValueError('Selecciona un proyecto para la prueba.')
        if not proyecto:
            raise ValueError('Tu proyecto debe estar registrado en Dataper.')
        datos, unidad, galones = datos_pedido(request.form, proyecto, prueba=prueba)
        if prueba:
            unidad = 'prueba:' + unidad
        bloquear_cambios()
        unidad_libre(unidad)
        sol = Solicitud(tecnico_id=persona['id'], proyecto=proyecto, unidad=unidad,
                        datos={**datos, 'tecnico': persona['nombre']}, solicitado=galones)
        db.session.add(sol)
        db.session.commit()
    except ValueError as exc:
        return error(exc)
    ruta = 'abastecimiento.prueba_pedidos' if prueba else 'abastecimiento.entrada'
    return jsonify(ok=True, id=sol.id, destino=url_for(ruta, seccion='bandeja', _anchor=f'pedido-{sol.id}'))


@bp.post('/form-pruebas/abastecimiento/<int:sid>/<accion>')
@tecnico
def evidencias(sid, accion):
    exigir_mobile()
    comprobar_csrf()
    return registrar_evidencias(sid, accion, g.tecnico['id'])


def registrar_evidencias(sid, accion, tecnico_id):
    bloquear_cambios()
    sol = Solicitud.query.filter_by(id=sid, tecnico_id=tecnico_id).first_or_404()
    try:
        if accion == 'referencias' and sol.estado != 'cerrado':
            sol.datos = {**sol.datos, **referencias_pedido(request.form, sol.datos)}
        elif accion == sol.estado == 'llenado':
            cargado = cantidad(request.form.get('cargado'), 'galones cargados', Decimal('0.01'))
            if cargado > sol.autorizado:
                raise ValueError(f'El llenado no puede superar los {sol.autorizado} galones autorizados.')
            for tipo in FOTOS_LLENADO:
                guardar_foto(sol, tipo)
            sol.cargado = cargado
            sol.estado = 'recarga'
        elif accion == sol.estado == 'recarga':
            referencias = referencias_pedido(request.form, sol.datos, cierre=True)
            consumido = cantidad(request.form.get('consumido'), 'galones usados')
            disponible = sol.saldo_previo + sol.cargado
            if consumido > disponible:
                raise ValueError(f'El consumo no puede superar los {disponible} galones disponibles.')
            for tipo in FOTOS_RECARGA:
                guardar_foto(sol, tipo)
            sol.datos = {**sol.datos, **referencias}
            sol.consumido, sol.saldo_final, sol.estado = consumido, disponible - consumido, 'cerrado'
        else:
            raise ValueError('La acción ya no está disponible. Actualiza la página.')
        db.session.commit()
    except ValueError as exc:
        return error(exc)
    return jsonify(ok=True)


def mostrar_foto(sid, tipo):
    foto = db.get_or_404(AbastecimientoFoto, (sid, tipo))
    respuesta = send_file(io.BytesIO(foto.contenido), mimetype=foto.mime)
    respuesta.headers['Cache-Control'] = 'no-store, private'
    respuesta.headers['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@bp.get('/form-pruebas/abastecimiento/<int:sid>/foto/<tipo>')
@tecnico
def foto_tecnico(sid, tipo):
    exigir_mobile()
    Solicitud.query.filter_by(id=sid, tecnico_id=g.tecnico['id']).first_or_404()
    return mostrar_foto(sid, tipo)


@bp.get('/abastecimiento/<int:sid>/foto/<tipo>')
@login_required
def foto_gestion(sid, tipo):
    _, rol, proyectos = alcance()
    sol = db.get_or_404(Solicitud, sid)
    if rol not in ADMIN and sol.proyecto not in proyectos:
        abort(404)
    return mostrar_foto(sid, tipo)


def persona_prueba():
    _, rol, _ = alcance()
    if rol not in ADMIN:
        abort(403)
    return {'id': -session['user_id'], 'nombre': 'Técnico de prueba',
            'proyecto': '', 'departamento': '', 'supervisor': ''}


@bp.get('/abastecimiento/prueba/')
@login_required
def prueba_tecnico():
    persona = persona_prueba()
    ultimo = Solicitud.query.filter_by(tecnico_id=persona['id']).order_by(Solicitud.id.desc()).first()
    qr_listo = Solicitud.query.filter_by(tecnico_id=persona['id'], estado='llenado').first() is not None
    return render_template('abastecimiento_prueba_inicio.html', persona=persona,
                           proyecto=ultimo.proyecto if ultimo else 'CLARO', qr_abastecimiento=qr_listo)


@bp.get('/abastecimiento/prueba/pedidos')
@login_required
def prueba_pedidos():
    return pantalla_tecnico(persona_prueba(), prueba=True)


@bp.post('/abastecimiento/prueba/solicitar')
@login_required
def prueba_solicitar():
    comprobar_csrf()
    return crear_pedido(persona_prueba(), prueba=True)


@bp.post('/abastecimiento/prueba/<int:sid>/<accion>')
@login_required
def prueba_evidencias(sid, accion):
    comprobar_csrf()
    return registrar_evidencias(sid, accion, persona_prueba()['id'])
