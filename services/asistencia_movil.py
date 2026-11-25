"""Asistencia individual desde Nucleus Mobile: cada técnico marca la suya (con vehículo o a pie, con compañero o solo)."""
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
from services.personal import cargo_homologado
from services.utilidades import ahora_peru

PLACA = re.compile(r'^[A-Z0-9]{2,4}-?[A-Z0-9]{2,4}$')
# Cargos que no salen a campo: no aparecen como compañeros.
CARGOS_OFICINA = re.compile(r'SUPERVIS|GESTOR|COORDINA|ALMACEN|ENCARGAD|PROPIETARI|ADMINISTRA|ASISTENTE|JEFE DE PROYECTO', re.I)


def instalar():
    """create_all no agrega columnas a tablas que ya existen (Neon): se añaden aquí."""
    from sqlalchemy import inspect
    if 'asistencia_cuadrilla' not in inspect(db.engine).get_table_names():
        return
    columnas = {c['name'] for c in inspect(db.engine).get_columns('asistencia_cuadrilla')}
    if 'movilidad' not in columnas:
        db.session.execute(db.text("ALTER TABLE asistencia_cuadrilla ADD COLUMN movilidad VARCHAR(12) NOT NULL DEFAULT 'VEHICULO'"))
        db.session.commit()


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
            'cargo': cargo_homologado(texto('CARGO')) or texto('CARGO'),
            'celular': texto('CELULAR'), 'contrata': texto('CONTRATA')}


def juniors(tecnico):
    """Compañeros posibles: personal de campo ACTIVO en Dataper del mismo proyecto; primero los de cargo Junior."""
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
        if CARGOS_OFICINA.search(cargo):
            continue
        cargo = cargo_homologado(cargo) or cargo
        lista.append({'id': fila.id, 'nombre': nombre, 'cargo': cargo, 'documento': str(valor(d, 'DOCUMENTO') or fila.key_value),
                      'junior': 'JUNIOR' in cargo.upper()})
    lista.sort(key=lambda x: (not x['junior'], x['nombre'].upper()))
    return lista


def de_hoy(documento):
    """Asistencia vigente que la persona marcó hoy (es individual: el compañero marca la suya).

    Si se la rechazaron, no cuenta: debe volver a subir su foto para seguir usando Nucleus Mobile."""
    return (AsistenciaCuadrilla.query.filter_by(fecha=ahora_peru().date(), documento=documento)
            .filter(AsistenciaCuadrilla.validacion != 'RECHAZADA').first())


def rechazada_hoy(documento):
    return AsistenciaCuadrilla.query.filter_by(fecha=ahora_peru().date(), documento=documento, validacion='RECHAZADA').first()


def ultimo_rechazo(documento):
    registro = (AsistenciaCuadrilla.query
                .filter(AsistenciaCuadrilla.validacion == 'RECHAZADA', AsistenciaCuadrilla.documento == documento)
                .order_by(AsistenciaCuadrilla.validado_en.desc(), AsistenciaCuadrilla.id.desc()).first())
    if registro:
        return {'fecha': registro.fecha.strftime('%d/%m/%Y'), 'motivo': registro.motivo, 'hoy': registro.fecha == ahora_peru().date()}
    return None


def a_dict(r):
    return {'id': r.id, 'fecha': r.fecha.isoformat(), 'nombre': r.nombre, 'documento': r.documento, 'proyecto': r.proyecto,
            'junior': r.junior_nombre, 'junior_documento': r.junior_documento, 'placa': r.placa,
            'movilidad': r.movilidad or 'VEHICULO', 'a_pie': (r.movilidad or '') == 'A_PIE', 'solo': not r.junior_documento,
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


def _foto_con_datos(archivo, texto, limite=1800):
    """Superpone los datos de asistencia en la esquina inferior derecha."""
    contenido = archivo.read(20 * 1024 * 1024 + 1)
    if not contenido:
        raise ValueError('Toma tu foto de asistencia.')
    if len(contenido) > 20 * 1024 * 1024:
        raise ValueError('La foto debe pesar como máximo 20 MB.')
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen = ImageOps.exif_transpose(imagen).convert('RGB')
            imagen.thumbnail((limite, limite))
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


def nombre_foto_perfil(datos):
    nombre = datos.get('_foto_perfil_mobile')
    return nombre if isinstance(nombre, str) and re.fullmatch(r'perfil/[a-f0-9]{32}\.jpg', nombre) else ''


def guardar_foto_perfil(archivo):
    if not archivo or not archivo.filename:
        raise ValueError('Toma tu foto de perfil.')
    nombre = 'perfil/' + uuid.uuid4().hex + '.jpg'
    _guardar(nombre, _foto_con_datos(archivo, [], limite=640))
    return nombre


def registrar(tecnico, form, archivo, dispositivo=''):
    if de_hoy(tecnico['documento']):
        raise ValueError('Ya registraste tu asistencia de hoy.')
    movilidad = 'A_PIE' if str(form.get('movilidad') or '').strip().lower() in ('a_pie', 'pie', 'a pie') else 'VEHICULO'
    junior = None
    if str(form.get('companero') or 'con').strip().lower() != 'solo':
        try:
            junior_id = int(form.get('junior') or 0)
        except ValueError:
            junior_id = 0
        junior = next((j for j in juniors(tecnico) if j['id'] == junior_id), None)
        if not junior:
            raise ValueError('Elige a tu compañero de la lista o marca que trabajas solo.')
    placa = ''
    if movilidad == 'VEHICULO':
        placa = re.sub(r'\s+', '', str(form.get('placa') or '')).upper()
        if not PLACA.match(placa):
            raise ValueError('Escribe la placa del vehículo (por ejemplo ABC-123) o marca que vas a pie.')
    lat = _numero(form.get('latitud'), -90, 90, 'latitud')
    lng = _numero(form.get('longitud'), -180, 180, 'longitud')
    try:
        precision = round(float(form.get('precision')), 1)
    except (TypeError, ValueError):
        precision = None
    if archivo is None or not archivo.filename:
        raise ValueError('Toma tu foto de asistencia.')
    ahora = ahora_peru()
    meses = ('ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.',
             'jul.', 'ago.', 'sep.', 'oct.', 'nov.', 'dic.')
    hora = ahora.strftime('%I:%M:%S').lstrip('0')
    periodo = 'a. m.' if ahora.hour < 12 else 'p. m.'
    texto = [f'{ahora.day} {meses[ahora.month - 1]} {ahora.year}, {hora} {periodo}',
             f'{lat:.6f}, {lng:.6f}',
             f"Placa {placa}" if placa else 'A pie',
             f"{tecnico['nombre']} con {junior['nombre']}" if junior else f"{tecnico['nombre']} (solo)"]
    salida = _foto_con_datos(archivo, texto)
    nombre = '%s/%s.jpg' % (ahora.strftime('%Y-%m'), uuid.uuid4().hex)
    _guardar(nombre, salida)
    datos = dict(personal_id=tecnico['id'], nombre=tecnico['nombre'], proyecto=tecnico.get('proyecto') or '',
                 junior_id=junior['id'] if junior else None, junior_documento=junior['documento'] if junior else '',
                 junior_nombre=junior['nombre'] if junior else '', placa=placa, movilidad=movilidad,
                 foto=nombre, latitud=lat, longitud=lng, precision_m=precision, registrado_en=ahora,
                 dispositivo=str(dispositivo or '')[:64])
    # Asistencia de hoy rechazada: se reemplaza con la nueva foto y vuelve a quedar por validar.
    registro = rechazada_hoy(tecnico['documento'])
    if registro:
        for campo, valor in datos.items():
            setattr(registro, campo, valor)
        registro.validacion, registro.validado_por, registro.validado_en = 'PENDIENTE', '', None
        registro.motivo = ('Volvió a subir la foto. Rechazo anterior: ' + (registro.motivo or ''))[:500]
    else:
        registro = AsistenciaCuadrilla(fecha=ahora.date(), documento=tecnico['documento'], **datos)
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
    """Puntos del día de quien marcó, en orden, con distancia a la marcación."""
    from models import UbicacionMovil
    filas = (UbicacionMovil.query.filter(UbicacionMovil.fecha == registro.fecha, UbicacionMovil.documento == registro.documento)
             .order_by(UbicacionMovil.hora).all())
    origen = (registro.latitud, registro.longitud)
    puntos = []
    for f in filas:
        puntos.append({'hora': f.hora.strftime('%H:%M'), 'evento': f.evento, 'latitud': f.latitud, 'longitud': f.longitud,
                       'precision': f.precision_m, 'quien': 'Principal',
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


def companero_marco(registro):
    """Asistencia propia del compañero ese día (None si no marcó)."""
    if not registro.junior_documento:
        return None
    return AsistenciaCuadrilla.query.filter_by(fecha=registro.fecha, documento=registro.junior_documento).first()


def detalle(registro):
    puntos = recorrido(registro)
    avisos = alertas(registro, puntos)
    for p in puntos:
        p.pop('_t')
    otro = companero_marco(registro)
    if registro.junior_documento and not otro:
        avisos.append('Su compañero %s no marcó asistencia ese día.' % registro.junior_nombre)
    return {**a_dict(registro), 'recorrido': puntos, 'alertas': avisos,
            'companero_hora': otro.registrado_en.strftime('%H:%M') if otro else ''}


# ── Planilla de Dataper: marcas de Mobile y faltas automáticas ──────────────

def marcas_periodo(base, inicio, fin):
    """{(personal_id, proyecto_id): {dia: marca propia de Mobile}}, quién lo puso como compañero ese día y
    la primera fecha en que cada persona aparece en Mobile (desde ahí cuenta la falta automática)."""
    from sqlalchemy import func
    claves = {}
    for clave in base:
        claves.setdefault(clave[0], []).append(clave)
    salida, nombrado = {}, {}
    for r in AsistenciaCuadrilla.query.filter(AsistenciaCuadrilla.fecha >= inicio, AsistenciaCuadrilla.fecha <= fin):
        for clave in claves.get(r.personal_id, []):
            salida.setdefault(clave, {})[r.fecha.day] = {'id': r.id, 'validacion': r.validacion,
                                                         'hora': r.registrado_en.strftime('%H:%M'), 'placa': r.placa,
                                                         'a_pie': (r.movilidad or '') == 'A_PIE', 'companero': r.junior_nombre}
        for clave in claves.get(r.junior_id, []):
            nombrado.setdefault(clave, {})[r.fecha.day] = r.nombre
    primera = {}
    for columna in (AsistenciaCuadrilla.personal_id, AsistenciaCuadrilla.junior_id):
        for pid, fecha in db.session.query(columna, func.min(AsistenciaCuadrilla.fecha)).group_by(columna):
            if pid is not None and (pid not in primera or fecha < primera[pid]):
                primera[pid] = fecha
    return salida, nombrado, primera


def completar_planilla(personas, inicio, fin):
    """Agrega a la planilla lo marcado en Mobile (P pendiente de validar) y la falta automática.

    La falta automática solo aplica a quien ya usa Mobile (desde su primera marca), en días pasados
    y sin contar domingos. Una marca guardada a mano siempre manda."""
    from datetime import timedelta
    base = {(p['personal_id'], p['proyecto_id']): p for p in personas}
    movil, nombrado, primera = marcas_periodo(base, inicio, fin)
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
                quien = nombrado.get(clave, {}).get(dia.day)
                nota = 'No marcó en Nucleus Mobile' + (' (%s lo puso como compañero)' % quien if quien else '')
                p['marcas'][n] = {'estado': 'FALTA', 'observacion': nota, 'version': 0, 'auto': True}
            dia += timedelta(days=1)
    return personas
