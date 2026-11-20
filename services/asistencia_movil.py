"""Asistencia de cuadrilla desde Nucleus Mobile: principal + junior + placa + foto con coordenadas."""
import io
import json
import os
import re
import unicodedata
import uuid

from flask import current_app
from PIL import Image, ImageDraw, ImageFont, ImageOps

from db import db
from models import AsistenciaCuadrilla, NucleusData, Proyecto
from services.formularios_prueba import valor
from services.utilidades import ahora_peru

PLACA = re.compile(r'^[A-Z0-9]{2,4}-?[A-Z0-9]{2,4}$')


def _dataper():
    modulo = Proyecto.query.filter_by(nombre='Dataper').first()
    if not modulo:
        return []
    filas = []
    for fila in NucleusData.query.filter_by(proyecto_id=modulo.id):
        try:
            d = json.loads(fila.data_json or '{}')
        except ValueError:
            continue
        if isinstance(d, dict):
            filas.append((fila, d))
    return filas


def ficha(tecnico):
    """Datos de Dataper del técnico que inició sesión."""
    fila = db.session.get(NucleusData, tecnico['id'])
    d = json.loads(fila.data_json or '{}') if fila else {}
    texto = lambda k: str(valor(d, k) or '').strip()
    return {'nombre': tecnico['nombre'], 'documento': tecnico['documento'], 'proyecto': tecnico['proyecto'],
            'departamento': tecnico.get('departamento') or texto('DEPARTAMENTO'), 'supervisor': tecnico.get('supervisor') or texto('SUPERVISOR'),
            'cargo': texto('CARGO'), 'celular': texto('CELULAR'), 'contrata': texto('CONTRATA')}


def juniors(tecnico):
    """Personal activo de Dataper del mismo proyecto; primero los de cargo Junior."""
    proyecto = str(tecnico.get('proyecto') or '').strip().upper()
    lista = []
    for fila, d in _dataper():
        if fila.id == tecnico['id'] or str(valor(d, 'ESTADO') or '').strip().upper() != 'ACTIVO':
            continue
        if str(valor(d, 'PROYECTO') or '').strip().upper() != proyecto:
            continue
        nombre = str(valor(d, 'TECNICO') or '').strip()
        if not nombre:
            continue
        cargo = str(valor(d, 'CARGO') or '').strip()
        lista.append({'id': fila.id, 'nombre': nombre, 'cargo': cargo, 'documento': str(valor(d, 'DOCUMENTO') or fila.key_value),
                      'junior': 'JUNIOR' in cargo.upper()})
    lista.sort(key=lambda x: (not x['junior'], x['nombre'].upper()))
    return lista


def de_hoy(documento):
    """Asistencia de hoy donde la persona aparece como principal o como junior."""
    return (AsistenciaCuadrilla.query.filter_by(fecha=ahora_peru().date())
            .filter((AsistenciaCuadrilla.documento == documento) | (AsistenciaCuadrilla.junior_documento == documento)).first())


def ultimo_rechazo(documento):
    registro = (AsistenciaCuadrilla.query
                .filter(AsistenciaCuadrilla.validacion == 'RECHAZADA',
                        (AsistenciaCuadrilla.documento == documento) |
                        (AsistenciaCuadrilla.junior_documento == documento))
                .order_by(AsistenciaCuadrilla.validado_en.desc(), AsistenciaCuadrilla.id.desc()).first())
    if registro:
        return {'fecha': registro.fecha.strftime('%d/%m/%Y'), 'motivo': registro.motivo}
    return None


def a_dict(r):
    return {'id': r.id, 'fecha': r.fecha.isoformat(), 'nombre': r.nombre, 'documento': r.documento, 'proyecto': r.proyecto,
            'junior': r.junior_nombre, 'junior_documento': r.junior_documento, 'placa': r.placa,
            'latitud': r.latitud, 'longitud': r.longitud, 'precision': r.precision_m,
            'hora': r.registrado_en.strftime('%H:%M'), 'registrado_en': r.registrado_en.isoformat(sep=' ', timespec='minutes'),
            'validacion': r.validacion, 'validado_por': r.validado_por, 'motivo': r.motivo,
            'validado_en': r.validado_en.isoformat(sep=' ', timespec='minutes') if r.validado_en else ''}


def _numero(v, minimo, maximo, nombre):
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ValueError('No llegó tu ubicación. Activa el GPS y vuelve a tomar la foto.') from None
    if not minimo <= n <= maximo:
        raise ValueError('La %s no es válida. Vuelve a tomar la foto.' % nombre)
    return n


def _foto_con_datos(archivo, texto):
    """Superpone los datos de asistencia en la esquina inferior derecha."""
    contenido = archivo.read(20 * 1024 * 1024 + 1)
    if not contenido:
        raise ValueError('Toma la foto de la cuadrilla.')
    if len(contenido) > 20 * 1024 * 1024:
        raise ValueError('La foto debe pesar como máximo 20 MB.')
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen = ImageOps.exif_transpose(imagen).convert('RGB')
            imagen.thumbnail((1800, 1800))
    except Exception:
        raise ValueError('La foto no se pudo abrir. Vuelve a tomarla.') from None
    tam = max(9, min(imagen.width // 27, imagen.height // 10))
    try:
        fuente = ImageFont.load_default(size=tam)
    except TypeError:
        fuente = ImageFont.load_default()
    # La fuente incluida no trae tildes ni ñ: se imprimen sin ellas.
    texto = [''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c)) for t in texto]
    margen = max(4, tam // 2)
    paso = max(tam + 2, round(tam * 1.3))
    derecha = imagen.width - margen
    abajo = imagen.height - margen
    dibujo = ImageDraw.Draw(imagen)
    for n, linea in enumerate(reversed(texto)):
        while linea and dibujo.textlength(linea, font=fuente) > imagen.width - 2 * margen:
            linea = linea[:-1]
        if linea != texto[-1 - n] and len(linea) > 3:
            linea = linea[:-3] + '...'
        dibujo.text((derecha, abajo - n * paso), linea, anchor='rd', fill='white',
                    font=fuente, stroke_width=max(1, tam // 24), stroke_fill='#181818')
    salida = io.BytesIO()
    imagen.save(salida, 'JPEG', quality=85)
    salida.seek(0)
    return salida


def _guardar(nombre, salida):
    from services.apoyo import b2_cliente, disco_efimero_sin_b2, evidencia_usa_b2
    if disco_efimero_sin_b2():
        raise ValueError('El almacenamiento de fotos no está configurado. Avisa al administrador.')
    if evidencia_usa_b2():
        b2_cliente().upload_fileobj(salida, current_app.config['B2_BUCKET'], 'asistencia/' + nombre)
        return
    ruta = os.path.join(current_app.config['EVIDENCIA_DIR'], 'asistencia', nombre)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'wb') as destino:
        destino.write(salida.getvalue())


def leer_foto(nombre):
    from services.apoyo import b2_cliente, evidencia_usa_b2
    if evidencia_usa_b2():
        return b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'], Key='asistencia/' + nombre)['Body'].read()
    with open(os.path.join(current_app.config['EVIDENCIA_DIR'], 'asistencia', nombre), 'rb') as origen:
        return origen.read()


def registrar(tecnico, form, archivo, dispositivo=''):
    previo = de_hoy(tecnico['documento'])
    if previo:
        raise ValueError('Ya registraste tu asistencia de hoy.' if previo.documento == tecnico['documento']
                         else '%s ya registró la asistencia de hoy contigo.' % previo.nombre)
    try:
        junior_id = int(form.get('junior') or 0)
    except ValueError:
        junior_id = 0
    junior = next((j for j in juniors(tecnico) if j['id'] == junior_id), None)
    if not junior:
        raise ValueError('Elige a tu junior de la lista.')
    if de_hoy(junior['documento']):
        raise ValueError('%s ya tiene asistencia registrada hoy en otra cuadrilla.' % junior['nombre'])
    placa = re.sub(r'\s+', '', str(form.get('placa') or '')).upper()
    if not PLACA.match(placa):
        raise ValueError('Escribe la placa del vehículo (por ejemplo ABC-123).')
    lat = _numero(form.get('latitud'), -90, 90, 'latitud')
    lng = _numero(form.get('longitud'), -180, 180, 'longitud')
    try:
        precision = round(float(form.get('precision')), 1)
    except (TypeError, ValueError):
        precision = None
    if archivo is None or not archivo.filename:
        raise ValueError('Toma la foto de la cuadrilla.')
    ahora = ahora_peru()
    meses = ('ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.',
             'jul.', 'ago.', 'sep.', 'oct.', 'nov.', 'dic.')
    hora = ahora.strftime('%I:%M:%S').lstrip('0')
    periodo = 'a. m.' if ahora.hour < 12 else 'p. m.'
    texto = [f'{ahora.day} {meses[ahora.month - 1]} {ahora.year}, {hora} {periodo}',
             f'{lat:.6f}, {lng:.6f}',
             f"Placa {placa}",
             f"{tecnico['nombre']} + {junior['nombre']}"]
    salida = _foto_con_datos(archivo, texto)
    nombre = '%s/%s.jpg' % (ahora.strftime('%Y-%m'), uuid.uuid4().hex)
    _guardar(nombre, salida)
    registro = AsistenciaCuadrilla(fecha=ahora.date(), personal_id=tecnico['id'], documento=tecnico['documento'],
                                   nombre=tecnico['nombre'], proyecto=tecnico.get('proyecto') or '', junior_id=junior['id'],
                                   junior_documento=junior['documento'], junior_nombre=junior['nombre'], placa=placa,
                                   foto=nombre, latitud=lat, longitud=lng, precision_m=precision, registrado_en=ahora,
                                   dispositivo=str(dispositivo or '')[:64])
    db.session.add(registro)
    db.session.commit()
    return registro


# ── Recorrido: un punto por cada acción en Nucleus Mobile ───────────────────

def leer_ubicacion(cabecera):
    """'lat,lng,precision' enviado por Nucleus Mobile; None si falta o no es válido."""
    try:
        partes = [float(x) for x in str(cabecera or '').split(',')[:3]]
    except ValueError:
        return None
    if len(partes) < 2 or not (-90 <= partes[0] <= 90 and -180 <= partes[1] <= 180) or partes[:2] == [0.0, 0.0]:
        return None
    return {'latitud': partes[0], 'longitud': partes[1], 'precision': partes[2] if len(partes) > 2 and partes[2] >= 0 else None}


def guardar_punto(documento, ubicacion, evento, dispositivo=''):
    from models import UbicacionMovil
    ahora = ahora_peru()
    db.session.add(UbicacionMovil(documento=documento, fecha=ahora.date(), hora=ahora, latitud=ubicacion['latitud'],
                                  longitud=ubicacion['longitud'], precision_m=ubicacion.get('precision'),
                                  evento=str(evento)[:60], dispositivo=str(dispositivo or '')[:64]))
    db.session.commit()


def distancia_km(a, b):
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def recorrido(registro):
    """Puntos del día del principal (y del junior), en orden, con distancia a la marcación."""
    from models import UbicacionMovil
    docs = [d for d in (registro.documento, registro.junior_documento) if d]
    filas = (UbicacionMovil.query.filter(UbicacionMovil.fecha == registro.fecha, UbicacionMovil.documento.in_(docs))
             .order_by(UbicacionMovil.hora).all())
    origen = (registro.latitud, registro.longitud)
    puntos = []
    for f in filas:
        puntos.append({'hora': f.hora.strftime('%H:%M'), 'evento': f.evento, 'latitud': f.latitud, 'longitud': f.longitud,
                       'precision': f.precision_m, 'quien': 'Junior' if f.documento != registro.documento else 'Principal',
                       'km': round(distancia_km(origen, (f.latitud, f.longitud)), 1), '_t': f.hora})
    return puntos


def alertas(registro, puntos):
    """Señales para que el gestor revise: no prueban trampa, solo avisan."""
    salida = []
    if registro.precision_m is not None and registro.precision_m > 100:
        salida.append('La ubicación al marcar tuvo baja precisión (±%d m).' % registro.precision_m)
    previos = (AsistenciaCuadrilla.query.filter(AsistenciaCuadrilla.documento == registro.documento,
                                                AsistenciaCuadrilla.id != registro.id, AsistenciaCuadrilla.dispositivo != '')
               .order_by(AsistenciaCuadrilla.fecha.desc()).limit(10).all())
    if registro.dispositivo and previos and registro.dispositivo not in {p.dispositivo for p in previos}:
        salida.append('Marcó desde un celular distinto al de días anteriores.')
    cercanos = [p for p in previos if distancia_km((p.latitud, p.longitud), (registro.latitud, registro.longitud)) < 0.15]
    if len(cercanos) >= 3:
        salida.append('Marcó en el mismo punto que otros %d días.' % len(cercanos))
    despues = [p for p in puntos if p['_t'] > registro.registrado_en and p['evento'] != 'Asistencia']
    if despues:
        p = despues[0]
        minutos = max(1, int((p['_t'] - registro.registrado_en).total_seconds() // 60))
        if p['km'] >= 10 and p['km'] / (minutos / 60) > 80:
            salida.append('Marcó y %d min después %s a %s km. No cuadra.' % (minutos, p['evento'].lower(), p['km']))
    anterior = None
    for p in puntos:
        if anterior:
            horas = max((p['_t'] - anterior['_t']).total_seconds() / 3600, 1 / 60)
            km = distancia_km((anterior['latitud'], anterior['longitud']), (p['latitud'], p['longitud']))
            if km >= 10 and km / horas > 120:
                salida.append('Salto de %d km en %d min entre %s y %s.' % (km, round(horas * 60), anterior['hora'], p['hora']))
                break
        anterior = p
    return salida


def detalle(registro):
    puntos = recorrido(registro)
    avisos = alertas(registro, puntos)
    for p in puntos:
        p.pop('_t')
    return {**a_dict(registro), 'recorrido': puntos, 'alertas': avisos}


# ── Planilla de Dataper: marcas de Mobile y faltas automáticas ──────────────

def marcas_periodo(base, inicio, fin):
    """{(personal_id, proyecto_id): {dia: marca de Mobile}} y la primera fecha en que cada persona marcó."""
    from sqlalchemy import func
    claves = {}
    for clave in base:
        claves.setdefault(clave[0], []).append(clave)
    salida = {}
    for r in AsistenciaCuadrilla.query.filter(AsistenciaCuadrilla.fecha >= inicio, AsistenciaCuadrilla.fecha <= fin):
        for pid, rol in ((r.personal_id, 'principal'), (r.junior_id, 'junior')):
            for clave in claves.get(pid, []):
                salida.setdefault(clave, {})[r.fecha.day] = {'id': r.id, 'validacion': r.validacion, 'rol': rol,
                                                             'hora': r.registrado_en.strftime('%H:%M'), 'placa': r.placa}
    primera = {}
    for columna in (AsistenciaCuadrilla.personal_id, AsistenciaCuadrilla.junior_id):
        for pid, fecha in db.session.query(columna, func.min(AsistenciaCuadrilla.fecha)).group_by(columna):
            if pid is not None and (pid not in primera or fecha < primera[pid]):
                primera[pid] = fecha
    return salida, primera


def completar_planilla(personas, inicio, fin):
    """Agrega a la planilla lo marcado en Mobile (P pendiente de validar) y la falta automática.

    La falta automática solo aplica a quien ya usa Mobile (desde su primera marca), en días pasados
    y sin contar domingos. Una marca guardada a mano siempre manda."""
    from datetime import timedelta
    base = {(p['personal_id'], p['proyecto_id']): p for p in personas}
    movil, primera = marcas_periodo(base, inicio, fin)
    hoy = ahora_peru().date()
    for clave, p in base.items():
        dias_movil = movil.get(clave, {})
        desde = primera.get(clave[0])
        dia = inicio
        while dia <= fin:
            n = str(dia.day)
            mv = dias_movil.get(dia.day)
            if n in p['marcas']:
                if mv:
                    p['marcas'][n]['movil'] = mv
            elif mv:
                p['marcas'][n] = {'estado': 'PRESENTE', 'observacion': 'Marcó en Mobile a las %s' % mv['hora'], 'version': 0, 'movil': mv}
            elif desde and desde <= dia < hoy and dia.weekday() != 6 and p.get('activo'):
                p['marcas'][n] = {'estado': 'FALTA', 'observacion': 'No marcó en Nucleus Mobile', 'version': 0, 'auto': True}
            dia += timedelta(days=1)
    return personas
