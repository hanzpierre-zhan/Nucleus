"""Caja Chica: solicitud del técnico por ítems, aislada de Rendición.

Flujo: PENDIENTE (gestora valida) → VALIDADO (responsable deposita) →
DEPOSITADO (el técnico rinde cada ítem; la gestora aprueba o rechaza cada uno;
un ítem rechazado vuelve a rendirse) → POR_DEVOLVER si gastó menos de lo
depositado → ARCHIVADO cuando todo está aprobado. ANULADO solo antes de depositar.
Un ítem rechazado que el técnico no puede sustentar pasa a DEVUELTO: su monto
se suma a la devolución (depositado − gastado aprobado).

Los rechazos no cierran la solicitud: la devuelven a la etapa anterior.
- En validación → RECHAZADO: vuelve al técnico, que corrige y reenvía (PENDIENTE).
- En depósito → PENDIENTE con motivo_rechazo: vuelve a validación.
"""
import io
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from flask import current_app
from PIL import Image, ImageOps
from sqlalchemy import Integer, String, cast
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db import db
from models import AppConfig, CajaChicaItem, CajaChicaSolicitud, Proyecto

MODULO = 'Caja Chica'
MAX_ITEMS = 20
MAX_FOTOS = 5
MAX_COMPROBANTES = 10
# SUSTENTO: todo resuelto, la gestión lo revisa y lo archiva. Para el técnico ya terminó.
ESTADOS_FINALES = ('SUSTENTO', 'ARCHIVADO', 'ANULADO')


def instalar():
    """Proyecto vacío solo para asignar el acceso al módulo desde Usuarios."""
    if not Proyecto.query.filter_by(nombre=MODULO).first():
        db.session.add(Proyecto(nombre=MODULO, icono='fa-cash-register'))
        db.session.commit()
    # create_all no agrega columnas a tablas existentes (Neon): se añaden aquí.
    from sqlalchemy import inspect
    columnas = {c['name'] for c in inspect(db.engine).get_columns('caja_chica_solicitudes')}
    if 'depositado_en' not in columnas:
        db.session.execute(db.text('ALTER TABLE caja_chica_solicitudes ADD COLUMN depositado_en TIMESTAMP'))
        db.session.commit()
    if 'devolucion_aceptada' not in columnas:
        db.session.execute(db.text('ALTER TABLE caja_chica_solicitudes ADD COLUMN devolucion_aceptada BOOLEAN DEFAULT FALSE'))
        db.session.commit()
    columnas = {c['name'] for c in inspect(db.engine).get_columns('caja_chica_items')}
    for nombre, tipo in (('razon_social', 'VARCHAR(200)'), ('evidencia', 'VARCHAR(120)'),
                         ('comprobantes', 'TEXT'), ('evidencias', 'TEXT')):
        if nombre not in columnas:
            db.session.execute(db.text('ALTER TABLE caja_chica_items ADD COLUMN %s %s' % (nombre, tipo)))
            db.session.commit()


# Usuarios administrativos que, desde el celular, entran directo a depositar Caja Chica.
CLAVE_DEPOSITANTES = 'depositantes_movil'


def depositantes():
    modulo = Proyecto.query.filter_by(nombre=MODULO).first()
    cfg = modulo and AppConfig.query.filter_by(proyecto_id=modulo.id, clave=CLAVE_DEPOSITANTES).first()
    try:
        return {int(i) for i in json.loads(cfg.valor or '[]')} if cfg else set()
    except (TypeError, ValueError):
        return set()


def marcar_depositante(usuario_id, activo):
    modulo = Proyecto.query.filter_by(nombre=MODULO).first()
    _exigir(modulo, 'No existe el módulo Caja Chica.')
    actuales = depositantes()
    if activo:
        actuales.add(int(usuario_id))
    else:
        actuales.discard(int(usuario_id))
    cfg = AppConfig.query.filter_by(proyecto_id=modulo.id, clave=CLAVE_DEPOSITANTES).first()
    if cfg is None:
        cfg = AppConfig(proyecto_id=modulo.id, clave=CLAVE_DEPOSITANTES)
        db.session.add(cfg)
    cfg.valor = json.dumps(sorted(actuales))
    db.session.commit()


def es_celular(user_agent):
    return bool(re.search(r'Mobi|Android|iPhone|iPod', str(user_agent or '')))


# Cuenta a la que el técnico devuelve el saldo no gastado.
CUENTA_DEVOLUCION = {'tipo': 'Plin', 'titular': 'Jessica Cordero', 'numero': '988191318'}


def dataper_por_documento(documentos):
    """{documento: {'registrado': bool, 'supervisor': str, 'departamento': str}} según Dataper (activo = registrado)."""
    from models import NucleusData
    from services.formularios_prueba import documento as limpiar, valor
    buscados = {limpiar(d) for d in documentos if d}
    resultado = {d: {'registrado': False, 'supervisor': '', 'departamento': ''} for d in buscados}
    if not buscados:
        return resultado
    filas = (NucleusData.query.join(Proyecto, Proyecto.id == NucleusData.proyecto_id)
             .filter(Proyecto.nombre == 'Dataper').with_entities(NucleusData.data_json))
    for (crudo,) in filas:
        try:
            data = json.loads(crudo or '{}')
        except ValueError:
            continue
        doc = limpiar(valor(data, 'DOCUMENTO'))
        if doc not in buscados:
            continue
        activo = str(valor(data, 'ESTADO')).strip().upper() == 'ACTIVO'
        actual = resultado[doc]
        if activo or not actual['registrado']:
            actual['registrado'] = actual['registrado'] or activo
            actual['supervisor'] = str(valor(data, 'SUPERVISOR')).strip() or actual['supervisor']
            actual['departamento'] = str(valor(data, 'DEPARTAMENTO')).strip() or actual['departamento']
    return resultado


def dinero(valor):
    return format(Decimal(valor or 0).quantize(Decimal('0.01')), '.2f')


def _historial(sol, accion, usuario, motivo='', conceptos=None, revision=None, envio_tecnico=None, formulario=None):
    registros = json.loads(sol.historial or '[]')
    evento = {'accion': accion, 'usuario': usuario, 'fecha': datetime.utcnow().isoformat(timespec='seconds'),
              'estado': sol.estado, 'motivo': motivo}
    if conceptos is not None:
        evento['conceptos'] = conceptos
    if revision is not None:
        evento['revision'] = revision
    if envio_tecnico is not None:
        evento['envio_tecnico'] = envio_tecnico
    if formulario is not None:
        evento['formulario'] = formulario
    registros.append(evento)
    sol.historial = json.dumps(registros, ensure_ascii=False)


def _exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


# ── Técnico ────────────────────────────────────────────────────────────────

def por_proyecto(valor, proyectos):
    """Correo/cotización por proyecto. Acepta el formato antiguo (un solo Sí/No para todos)."""
    if isinstance(valor, dict):
        return {p: valor.get(p) is True for p in proyectos}
    return {p: valor is True for p in proyectos}


def catalogo_por_proyecto(catalogo, proyectos):
    return [dict(fila, correo=por_proyecto(fila.get('correo'), proyectos),
                 cotizacion=por_proyecto(fila.get('cotizacion'), proyectos)) for fila in catalogo]


def normalizar_catalogo(filas, proyectos):
    _exigir(isinstance(filas, list) and len(filas) <= 200, 'El catálogo admite hasta 200 conceptos.')
    nombres, catalogo = set(), []
    for fila in filas:
        _exigir(isinstance(fila, dict), 'Concepto inválido.')
        nombre = str(fila.get('nombre') or '').strip()
        descripcion = str(fila.get('descripcion') or '').strip()
        reglas = fila.get('proyectos')
        _exigir(nombre and len(nombre) <= 80 and len(descripcion) <= 300, 'Revisa el nombre y la descripción del concepto.')
        _exigir(nombre.casefold() not in nombres, 'Hay un concepto duplicado: %s.' % nombre)
        _exigir(isinstance(reglas, dict) and set(reglas) == set(proyectos)
                and all(v in ('', 'Gasto Cobra', 'Refacturable') for v in reglas.values()),
                'Selecciona una clasificación válida para cada proyecto.')
        nombres.add(nombre.casefold())
        catalogo.append({'nombre': nombre, 'descripcion': descripcion, 'proyectos': reglas,
                         'correo': por_proyecto(fila.get('correo'), proyectos),
                         'cotizacion': por_proyecto(fila.get('cotizacion'), proyectos)})
    return catalogo


def _monto_vacio(valor):
    texto = str(valor if valor is not None else '').strip().replace('S/', '').replace(',', '.').strip()
    try:
        return not texto or Decimal(texto) == 0
    except Exception:
        return False


def _llenar(sol, datos, catalogo, proyectos, bancos, importe, anteriores=()):
    """Valida la cabecera y los ítems del técnico y los copia en la solicitud."""
    proyecto = str(datos.get('proyecto') or '').strip()
    _exigir(proyecto in proyectos, 'Selecciona un proyecto válido.')
    motivo = str(datos.get('motivo') or '').strip()
    _exigir(motivo and len(motivo) <= 500, 'Escribe el motivo de la solicitud (máximo 500 caracteres).')
    banco = str(datos.get('banco') or '').strip()
    _exigir(banco in bancos, 'Selecciona tu banco.')
    cuenta = re.sub(r'\s', '', str(datos.get('cuenta') or ''))
    _exigir(re.fullmatch(r'[0-9-]{6,40}', cuenta), 'Escribe un número de cuenta válido.')
    items = datos.get('items')
    _exigir(isinstance(items, list), 'Agrega entre 1 y %d ítems.' % MAX_ITEMS)
    # Un concepto marcado sin monto (vacío o 0) no se considera.
    items = [i for i in items if not (isinstance(i, dict) and _monto_vacio(i.get('monto')))]
    _exigir(1 <= len(items) <= MAX_ITEMS, 'Marca al menos un concepto con su monto (máximo %d).' % MAX_ITEMS)
    disponibles = {fila['nombre']: fila for fila in catalogo if fila['proyectos'].get(proyecto)}
    nuevos, conceptos, total = [], {}, Decimal('0')
    for n, item in enumerate(items, 1):
        _exigir(isinstance(item, dict), 'Ítem %d inválido.' % n)
        tipo = str(item.get('tipo_gasto') or '').strip()
        anterior = anteriores[n - 1] if proyecto == sol.proyecto and n <= len(anteriores) else {}
        if anterior.get('tipo_gasto') == tipo and (anterior.get('tipo_presupuesto') or tipo not in disponibles):
            regla = {'proyectos': {proyecto: anterior.get('tipo_presupuesto', '')},
                     'correo': anterior.get('requiere_correo', False),
                     'cotizacion': anterior.get('requiere_cotizacion', False)}
        else:
            _exigir(tipo in disponibles, 'Ítem %d: selecciona un tipo de gasto disponible para este proyecto.' % n)
            regla = dict(disponibles[tipo])
            regla['correo'] = por_proyecto(regla.get('correo'), [proyecto])[proyecto]
            regla['cotizacion'] = por_proyecto(regla.get('cotizacion'), [proyecto])[proyecto]
        # El técnico no da el correo: la gestora adjunta el correo de validación al validar
        # (requiere_correo). Aquí solo se acepta, opcional, desde la edición de gestión.
        correo = str(item.get('correo_validador') or '').strip() if regla['correo'] else ''
        _exigir(not correo or (len(correo) <= 254 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo)),
                'Ítem %d: el correo de quien valida no es válido.' % n)
        conceptos[str(n)] = {'tipo_presupuesto': regla['proyectos'][proyecto], 'correo_validador': correo,
                             'requiere_correo': regla['correo'], 'requiere_cotizacion': regla.get('cotizacion', False)}
        descripcion = str(item.get('descripcion') or '').strip()
        _exigir(len(descripcion) <= 300, 'Ítem %d: la descripción es muy larga.' % n)
        monto = importe(item.get('monto'))
        nuevos.append(CajaChicaItem(numero=n, tipo_gasto=tipo, descripcion=descripcion, monto=monto))
        total += monto
    sol.proyecto, sol.motivo, sol.banco, sol.cuenta, sol.total = proyecto, motivo, banco, cuenta, total
    sol.items = nuevos
    return conceptos


CM_PENDIENTE, SITE_PENDIENTE = 'CM PENDIENTE', 'SITE PENDIENTE'
_CODIGO_CM = re.compile(r'\b(CM|PM|PLM|INC)[\s_-]*(\d{8})[\s_-]*(\d{8})\b')
_CODIGO_INC = re.compile(r'\bINC[\s_-]*(\d{6,7})\b')


def normalizar_cm(valor):
    """Vacío → CM PENDIENTE. Si no, solo códigos válidos (CM-AAAAMMDD-NNNNNNNN, PM, PLM, INC); otro texto no se acepta."""
    texto = str(valor or '').strip().upper()
    if not texto or texto == CM_PENDIENTE:
        return CM_PENDIENTE
    codigos = ['%s-%s-%s' % m.groups() for m in _CODIGO_CM.finditer(texto)]
    resto = _CODIGO_CM.sub(' ', texto)
    codigos += ['INC-%s' % m.group(1) for m in _CODIGO_INC.finditer(resto)]
    resto = _CODIGO_INC.sub(' ', resto)
    _exigir(codigos and not re.sub(r'[\s,;/]|\bY\b', '', resto),
            'Escribe el CM como CM-AAAAMMDD-NNNNNNNN (o PM / PLM), o déjalo vacío.')
    return ', '.join(dict.fromkeys(codigos))


def cm_pendiente(valor):
    """Falta el CM: vacío, CM PENDIENTE o un texto que no es un código válido."""
    valor = str(valor or '').strip()
    try:
        return normalizar_cm(valor) in (CM_PENDIENTE, '') or normalizar_cm(valor) != valor
    except ValueError:
        return True


def site_pendiente(valor):
    return str(valor or '').strip().upper() in ('', SITE_PENDIENTE)


def datos_pendientes(sol, formulario):
    """Qué le falta a la solicitud (CM y/o site). Las anuladas no cuentan."""
    if sol.estado in ('ANULADO', 'ELIMINADO'):
        return []
    return [nombre for nombre, falta in (('CM', cm_pendiente(formulario.get('wo'))), ('Site', site_pendiente(formulario.get('site')))) if falta]


def completar_datos(sol, usuario, wo, site):
    """El gestor completa el CM y/o el site. No cambia el estado ni la etapa de la solicitud."""
    _exigir(sol.estado not in ('ANULADO', 'ELIMINADO'), 'La solicitud está anulada.')
    site = str(site or '').strip()
    _exigir(len(site) <= 150, 'El nombre del site admite hasta 150 caracteres.')
    actual = a_dict(sol)['formulario']
    nuevo = dict(actual, wo=normalizar_cm(wo), site=site or SITE_PENDIENTE)
    if nuevo != actual:
        _historial(sol, 'completar CM / site', usuario, formulario=nuevo)
        db.session.commit()


def datos_formulario(datos, supervisor, responsables):
    campos = {'site': 150, 'wo': 100, 'titular': 150}
    formulario = {campo: str(datos.get(campo) or '').strip() for campo in campos}
    _exigir(all(len(formulario[c]) <= limite for c, limite in campos.items()), 'Revisa la longitud de los datos de la solicitud.')
    formulario['wo'] = normalizar_cm(formulario['wo'])
    formulario['site'] = formulario['site'] or SITE_PENDIENTE
    billetera = str(datos.get('tipo_billetera') or 'No aplica')
    _exigir(billetera in ('No aplica', 'Yape', 'Plin'), 'Selecciona una billetera válida.')
    numero = str(datos.get('numero_billetera') or '').strip() if billetera != 'No aplica' else ''
    _exigir(billetera == 'No aplica' or re.fullmatch(r'[0-9]{9}', numero), 'Ingresa los 9 dígitos de Yape o Plin.')
    responsable_id = str(datos.get('responsable_validacion') or '')
    responsable = responsables.get(responsable_id, '')
    _exigir(not responsable_id or responsable, 'Selecciona un responsable asignado al proyecto.')
    return dict(formulario, supervisor=supervisor, tipo_billetera=billetera, numero_billetera=numero,
                responsable_validacion=responsable, responsable_validacion_id=responsable_id)


def crear(tecnico, datos, catalogo, proyectos, bancos, importe, formulario=None, revisar=None):
    """revisar(conceptos): opcional, valida las restricciones de Mobile antes de guardar."""
    sol = CajaChicaSolicitud(documento=tecnico['documento'], tecnico=tecnico['nombre'], estado='PENDIENTE')
    conceptos = _llenar(sol, datos, catalogo, proyectos, bancos, importe)
    if revisar:
        revisar(conceptos)
    _historial(sol, 'solicitar', tecnico['nombre'], conceptos=conceptos, formulario=formulario)
    proyecto_id = Proyecto.query.filter_by(nombre=MODULO).with_entities(Proyecto.id).scalar()
    insert = pg_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    contador = insert(AppConfig).values(proyecto_id=proyecto_id, clave='deposito_ultimo_codigo', valor='3000')
    contador = contador.on_conflict_do_update(
        index_elements=['proyecto_id', 'clave'],
        set_={'valor': cast(cast(AppConfig.valor, Integer) + 1, String)},
    ).returning(AppConfig.valor)
    numero = int(db.session.execute(contador).scalar_one())
    sol.codigo = f'COB-{numero:05d}'
    db.session.add(sol)
    db.session.commit()
    return sol


def reenviar(sol, tecnico, datos, catalogo, proyectos, bancos, importe, formulario=None):
    """El técnico corrige una solicitud rechazada en validación y la reenvía."""
    _exigir(sol.documento == tecnico['documento'], 'Esta solicitud no es tuya.')
    _exigir(sol.estado == 'RECHAZADO', 'Solo se corrige una solicitud rechazada.')
    conceptos = _llenar(sol, datos, catalogo, proyectos, bancos, importe)
    sol.estado, sol.motivo_rechazo = 'PENDIENTE', None
    _historial(sol, 'reenviar', tecnico['nombre'], conceptos=conceptos, revision={}, formulario=formulario)
    db.session.commit()


def preparar_rendicion(sol, item, documento, comprobantes, importe):
    """Valida los comprobantes antes de guardar fotos. Cada uno: {ruc, razon_social, comprobante, monto}."""
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(sol.estado == 'DEPOSITADO', 'Solo se rinde una solicitud depositada.')
    _exigir(item.estado in ('POR_RENDIR', 'RECHAZADO'), 'Este ítem ya fue rendido.')
    _exigir(1 <= len(comprobantes) <= MAX_COMPROBANTES, 'Agrega entre 1 y %d comprobantes.' % MAX_COMPROBANTES)
    limpios, vistos = [], set()
    for n, datos in enumerate(comprobantes, 1):
        pre = 'Comprobante %d: ' % n if len(comprobantes) > 1 else ''
        ruc = re.sub(r'\D', '', str(datos.get('ruc') or ''))
        _exigir(len(ruc) == 11, pre + 'escribe el RUC del comprobante (11 dígitos).')
        numero = str(datos.get('comprobante') or '').strip().upper()
        _exigir(re.fullmatch(r'[A-Z0-9-]{3,40}', numero), pre + 'escribe el número de la boleta o factura.')
        _exigir((ruc, numero) not in vistos, pre + 'la boleta %s ya está en este gasto.' % numero)
        vistos.add((ruc, numero))
        try:
            monto = importe(datos.get('monto'))
        except ValueError as exc:
            raise ValueError(pre + str(exc)) from None
        # La razón social la completa el portal con la consulta de RUC; solo se guarda como referencia.
        limpios.append({'ruc': ruc, 'comprobante': numero, 'monto': monto,
                        'razon_social': str(datos.get('razon_social') or '').strip()[:200]})
    gastado = sum(c['monto'] for c in limpios)
    _exigir(gastado <= item.monto, 'El monto gastado (S/ %s) no puede superar el monto del ítem (S/ %s).'
            % (dinero(gastado), dinero(item.monto)))
    return limpios


def rendir_item(sol, item, documento, comprobantes, evidencias, importe=None):
    """comprobantes: salida de preparar_rendicion con 'fotos' (lista) en cada uno; evidencias: nombres de foto."""
    _exigir(all(1 <= len(c.get('fotos') or []) <= MAX_FOTOS for c in comprobantes),
            'Adjunta la foto de cada boleta o factura.')
    _exigir(evidencias, 'Adjunta la foto de la evidencia del gasto.')
    primero = comprobantes[0]
    item.ruc, item.comprobante = primero['ruc'], primero['comprobante']
    item.razon_social = primero['razon_social'] or None
    item.monto_gastado = sum(c['monto'] for c in comprobantes)
    item.fotos = json.dumps([f for c in comprobantes for f in c['fotos']])
    item.evidencia, item.evidencias = evidencias[0], json.dumps(evidencias)
    item.comprobantes = json.dumps([{**c, 'monto': dinero(c['monto'])} for c in comprobantes], ensure_ascii=False)
    item.estado, item.rendido_en, item.motivo_rechazo = 'EN_REVISION', datetime.utcnow(), None
    _historial(sol, 'rendir ítem %d' % item.numero, sol.tecnico)
    db.session.commit()


def devolver_item(sol, item, documento):
    """El técnico no usó (o no puede sustentar) un ítem: todo su monto pasa a la devolución."""
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(sol.estado == 'DEPOSITADO' and item.estado in ('POR_RENDIR', 'RECHAZADO'),
            'Solo se devuelve un ítem por rendir o rechazado.')
    item.estado, item.monto_gastado = 'DEVUELTO', Decimal('0')
    _historial(sol, 'devolver ítem %d' % item.numero, sol.tecnico)
    _cerrar_si_resuelto(sol, sol.tecnico)
    db.session.commit()


def deshacer_devolucion_item(sol, item, documento):
    """Desmarca un ítem devuelto mientras la devolución aún no se envió: vuelve a quedar por rendir."""
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(item.estado == 'DEVUELTO', 'Este ítem no está marcado para devolver.')
    _exigir(sol.estado == 'DEPOSITADO' or (sol.estado == 'POR_DEVOLVER' and not sol.devolucion_foto),
            'La devolución ya se envió; no se puede deshacer.')
    item.estado, item.monto_gastado, item.motivo_rechazo = 'POR_RENDIR', None, None
    sol.estado = 'DEPOSITADO'
    _historial(sol, 'deshacer devolución del ítem %d' % item.numero, sol.tecnico)
    db.session.commit()


def puede_devolver(sol):
    """La devolución se envía cuando ya no queda nada por rendir ni corregir, aunque falte la revisión."""
    if sol.devolucion_foto or diferencia(sol) <= 0:
        return False
    if sol.estado == 'POR_DEVOLVER':
        return True
    return sol.estado == 'DEPOSITADO' and all(i.estado in ('EN_REVISION', 'APROBADO', 'DEVUELTO') for i in sol.items)


def devolver(sol, documento, monto, foto, importe):
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(puede_devolver(sol), 'No hay devolución pendiente.')
    _exigir(importe(monto) == diferencia(sol), 'La devolución debe ser exactamente S/ %s.' % dinero(diferencia(sol)))
    sol.devolucion_monto, sol.devolucion_foto = diferencia(sol), foto
    _historial(sol, 'registrar devolución', sol.tecnico)
    db.session.commit()


# ── Gestión (Nucleus) ──────────────────────────────────────────────────────

TIEMPOS_RESPUESTA = ('Menor a 4 horas', 'Mayor a 4 horas', 'Atención Continua', 'No aplica')


def _tiempo_respuesta(tiempo):
    tiempo = str(tiempo or '').strip()
    _exigir(tiempo in ('',) + TIEMPOS_RESPUESTA, 'Elige un tiempo de respuesta válido.')
    return tiempo


def validar(sol, usuario, tiempo=None):
    _exigir(sol.estado == 'PENDIENTE', 'Solo se valida una solicitud pendiente.')
    datos = a_dict(sol, gestion=True)
    revision = datos['revision']
    _exigir(not any(i.get('requiere_correo') for i in datos['items']) or revision.get('archivo'),
            'Abre el código de la solicitud y adjunta el correo de validación.')
    _exigir(not any(i.get('requiere_cotizacion') for i in datos['items']) or revision.get('cotizacion'),
            'Abre el código de la solicitud e ingresa el número de cotización.')
    tiempo = _tiempo_respuesta(tiempo)
    sol.estado, sol.validado_por, sol.validado_en = 'VALIDADO', usuario, datetime.utcnow()
    sol.motivo_rechazo = None
    if tiempo:
        _historial(sol, 'validar', usuario, revision={**revision, 'tiempo': tiempo})
    else:
        _historial(sol, 'validar', usuario)
    db.session.commit()


def _documentos_revision(sol, cotizacion, archivo, revision, tiempo=None):
    cotizacion = str(cotizacion or '').strip()
    _exigir(len(cotizacion) <= 80, 'El número de cotización admite hasta 80 caracteres.')
    adjunto = revision.get('archivo', '')
    if archivo and archivo.filename:
        adjunto = guardar_correo(sol, archivo)
    tiempo = _tiempo_respuesta(tiempo if tiempo is not None else revision.get('tiempo'))
    return {'archivo': adjunto, 'cotizacion': cotizacion, 'tiempo': tiempo}


def guardar_documentos_revision(sol, usuario, cotizacion, archivo, tiempo=None):
    _exigir(sol.estado == 'PENDIENTE', 'Solo se pueden guardar documentos mientras la solicitud esté pendiente.')
    anterior = a_dict(sol, gestion=True)['revision']
    revision = _documentos_revision(sol, cotizacion, archivo, anterior, tiempo)
    if revision != anterior:
        _historial(sol, 'guardar documentos de validación', usuario, revision=revision)
        db.session.commit()


def editar_revision(sol, usuario, datos, archivo, catalogo, proyectos, bancos, importe):
    _exigir(sol.estado == 'PENDIENTE', 'Solo se edita una solicitud pendiente de validación.')
    anterior = a_dict(sol, gestion=True)
    envio = None
    if not anterior['envio_tecnico']:
        envio = {campo: anterior[campo] for campo in ('proyecto', 'motivo', 'banco', 'cuenta', 'total')}
        envio['formulario'] = anterior['formulario']
        envio['items'] = [
            {campo: item.get(campo) for campo in ('numero', 'tipo_gasto', 'descripcion', 'monto', 'tipo_presupuesto', 'correo_validador')}
            for item in anterior['items']
        ]
    conceptos = _llenar(sol, datos, catalogo, proyectos, bancos, importe, anteriores=anterior['items'])
    revision = _documentos_revision(sol, datos.get('cotizacion'), archivo, anterior['revision'])
    _historial(sol, 'editar solicitud', usuario, conceptos=conceptos,
               revision=revision, envio_tecnico=envio)
    db.session.commit()


def corregir_tecnico(sol, usuario, documento):
    """Corrige el DNI mal escrito: el técnico debe existir (ACTIVO y único) en Dataper; el nombre sale de ahí."""
    from services.formularios_prueba import buscar_personal, documento as limpiar
    nuevo = limpiar(documento)
    _exigir(re.fullmatch(r'[A-Z0-9]{8,15}', nuevo), 'Escribe un DNI o documento válido.')
    _exigir(nuevo != limpiar(sol.documento), 'Es el mismo documento que ya tiene la solicitud.')
    persona = buscar_personal(nuevo)
    _exigir(persona, 'Ese documento no está ACTIVO en Dataper (o está repetido). Corrígelo primero en Dataper.')
    anterior = '%s · %s' % (sol.documento, sol.tecnico)
    sol.documento, sol.tecnico = nuevo, persona['nombre'][:150]
    _historial(sol, 'corregir técnico', usuario, 'Antes: %s' % anterior)
    db.session.commit()


def rechazar(sol, usuario, motivo):
    """Devuelve la solicitud a la etapa anterior: validación → técnico, depósito → validación."""
    _exigir(sol.estado in ('PENDIENTE', 'VALIDADO'), 'Solo se rechaza en validación o en depósito.')
    _exigir(str(motivo or '').strip(), 'Escribe el motivo del rechazo.')
    motivo = motivo.strip()
    if sol.estado == 'PENDIENTE':
        sol.estado = 'RECHAZADO'
        _historial(sol, 'rechazar: vuelve al técnico', usuario, motivo)
    else:
        sol.estado, sol.validado_por, sol.validado_en = 'PENDIENTE', None, None
        _historial(sol, 'rechazar depósito: vuelve a validación', usuario, motivo)
    sol.motivo_rechazo = motivo
    db.session.commit()


def anular(sol, usuario, motivo):
    _exigir(sol.estado in ('PENDIENTE', 'VALIDADO', 'RECHAZADO'), 'Solo se anula antes del depósito.')
    _exigir(str(motivo or '').strip(), 'Escribe el motivo de la anulación.')
    sol.estado, sol.motivo_rechazo = 'ANULADO', motivo.strip()
    _historial(sol, 'anular', usuario, motivo.strip())
    db.session.commit()


def eliminar(solicitudes, usuario):
    """Retira la solicitud del módulo y conserva su correlativo y evidencias."""
    for sol in solicitudes:
        sol.estado = 'ELIMINADO'
        _historial(sol, 'eliminar', usuario)
    db.session.commit()


def depositar(sol, usuario, monto, foto, importe, comentario=''):
    """La fecha y hora se registran solas al confirmar (no las escribe el usuario). El comentario es opcional."""
    _exigir(sol.estado == 'VALIDADO', 'Solo se deposita una solicitud validada.')
    _exigir(importe(monto) == sol.total, 'El depósito debe ser el total solicitado (S/ %s).' % dinero(sol.total))
    _exigir(foto, 'Adjunta la foto del depósito.')
    ahora = datetime.utcnow()
    sol.estado, sol.deposito_monto, sol.depositado_en = 'DEPOSITADO', sol.total, ahora
    sol.deposito_fecha = (ahora - timedelta(hours=5)).strftime('%Y-%m-%d')  # día en Lima (UTC-5)
    sol.deposito_foto, sol.depositado_por = foto, usuario
    _historial(sol, 'depositar', usuario, str(comentario or '').strip()[:300])
    db.session.commit()


def revisar_item(sol, item, usuario, aprobar, motivo=''):
    _exigir(sol.estado == 'DEPOSITADO' and item.estado == 'EN_REVISION', 'Este ítem no está en revisión.')
    if aprobar:
        item.estado, item.motivo_rechazo = 'APROBADO', None
    else:
        _exigir(str(motivo or '').strip(), 'Escribe por qué se rechaza el ítem.')
        item.estado, item.motivo_rechazo = 'RECHAZADO', motivo.strip()
    item.revisado_por, item.revisado_en = usuario, datetime.utcnow()
    _historial(sol, ('aprobar' if aprobar else 'rechazar') + ' ítem %d' % item.numero, usuario, motivo or '')
    _cerrar_si_resuelto(sol, usuario)
    db.session.commit()


def corregir_monto(sol, item, usuario, montos, importe, comentario=''):
    """Al revisar: corrige lo gastado según la boleta (p. ej. 77 → 76).

    montos: uno por comprobante, en el mismo orden. Lo que deja de contar como gastado
    pasa al saldo del técnico (rendir o devolver), igual que un sobrante."""
    _exigir(sol.estado == 'DEPOSITADO' and item.estado == 'EN_REVISION', 'Este ítem no está en revisión.')
    comps = json.loads(item.comprobantes) if item.comprobantes else [
        {'ruc': item.ruc or '', 'razon_social': item.razon_social or '', 'comprobante': item.comprobante or '',
         'monto': dinero(item.monto_gastado or 0), 'fotos': json.loads(item.fotos or '[]')}]
    _exigir(isinstance(montos, list) and len(montos) == len(comps), 'Escribe el monto de cada comprobante.')
    nuevos = []
    for n, valor in enumerate(montos, 1):
        try:
            nuevos.append(importe(valor))
        except ValueError as exc:
            raise ValueError(('Comprobante %d: ' % n if len(comps) > 1 else '') + str(exc)) from None
    total = sum(nuevos, Decimal('0'))
    _exigir(total <= item.monto, 'El monto (S/ %s) no puede superar lo solicitado (S/ %s).' % (dinero(total), dinero(item.monto)))
    antes = item.monto_gastado or Decimal('0')
    _exigir(total != antes, 'El monto es el mismo.')
    comentario = str(comentario or '').strip()[:300]
    _exigir(comentario, 'Escribe por qué corriges el monto (le llega al técnico).')
    for c, m in zip(comps, nuevos):
        c['monto'] = dinero(m)
    item.comprobantes = json.dumps(comps, ensure_ascii=False)
    item.monto_gastado = total
    _historial(sol, 'corregir monto ítem %d' % item.numero, usuario,
               'S/ %s → S/ %s: %s' % (dinero(antes), dinero(total), comentario))
    db.session.commit()


def _cerrar_si_resuelto(sol, usuario):
    """Cuando ningún ítem queda por rendir, revisar o corregir: archiva o pide la devolución."""
    if all(i.estado in ('APROBADO', 'DEVUELTO') for i in sol.items):
        _cerrar_o_pedir_devolucion(sol, usuario)


def confirmar_devolucion(sol, usuario, aceptar, motivo=''):
    _exigir(sol.estado in ('POR_DEVOLVER', 'DEPOSITADO') and sol.devolucion_foto and not sol.devolucion_aceptada,
            'No hay devolución por revisar.')
    if aceptar:
        sol.devolucion_aceptada = True
        if sol.estado == 'POR_DEVOLVER':
            sol.estado = 'SUSTENTO'
            _historial(sol, 'confirmar devolución: pasa a sustento', usuario)
        else:
            # Faltan ítems por revisar: queda aprobada y se archiva al validar el último.
            _historial(sol, 'aprobar devolución', usuario)
    else:
        _exigir(str(motivo or '').strip(), 'Escribe por qué se rechaza la devolución.')
        sol.devolucion_monto = sol.devolucion_foto = None
        sol.devolucion_aceptada = False
        _historial(sol, 'rechazar devolución', usuario, motivo.strip())
    db.session.commit()


def diferencia(sol):
    gastado = sum((i.monto_gastado or Decimal('0') for i in sol.items), Decimal('0'))
    return (sol.deposito_monto or Decimal('0')) - gastado


def _cerrar_o_pedir_devolucion(sol, usuario):
    if sol.devolucion_foto and sol.devolucion_monto != diferencia(sol):
        # La devolución se envió antes de la revisión y luego cambió el monto: se pide de nuevo.
        _historial(sol, 'devolución enviada no coincide', usuario,
                   'Se envió S/ %s y corresponde S/ %s.' % (dinero(sol.devolucion_monto), dinero(max(diferencia(sol), Decimal('0')))))
        sol.devolucion_monto = sol.devolucion_foto = None
        sol.devolucion_aceptada = False
    if diferencia(sol) > 0 and sol.devolucion_foto and sol.devolucion_aceptada:
        sol.estado = 'SUSTENTO'
        _historial(sol, 'ítems resueltos y devolución aprobada: sustento', usuario)
    elif diferencia(sol) > 0:
        sol.estado = 'POR_DEVOLVER'
        _historial(sol, 'ítems resueltos: falta la devolución', usuario)
    else:
        sol.estado = 'SUSTENTO'
        _historial(sol, 'ítems resueltos: sustento', usuario)


def archivar(sol, usuario):
    # También se archiva lo aprobado que espera la devolución u otros ítems (lo demás queda cerrado).
    pendiente = sol.estado in ('POR_DEVOLVER', 'DEPOSITADO') and any(i.estado == 'APROBADO' for i in sol.items)
    _exigir(sol.estado == 'SUSTENTO' or pendiente, 'Solo se archiva una solicitud sustentada.')
    nota = ''
    if sol.estado == 'POR_DEVOLVER' and diferencia(sol) > 0:
        nota = 'Sin la devolución de S/ %s.' % dinero(diferencia(sol))
    elif sol.estado == 'DEPOSITADO':
        nota = 'Con ítems sin aprobar.'
    sol.estado, sol.archivado_en = 'ARCHIVADO', datetime.utcnow()
    _historial(sol, 'archivar', usuario, nota)
    db.session.commit()


def rechazar_sustentada(sol, usuario, motivo):
    """Sustentado o Archivado → Por rendir: los ítems aprobados vuelven al técnico como rechazados, con el motivo.

    También sirve cuando lo aprobado está en Sustentado pero la solicitud espera la devolución
    (POR_DEVOLVER) u otros ítems (DEPOSITADO)."""
    _exigir(sol.estado in ('SUSTENTO', 'ARCHIVADO')
            or (sol.estado in ('POR_DEVOLVER', 'DEPOSITADO') and any(i.estado == 'APROBADO' for i in sol.items)),
            'Solo se rechaza una solicitud sustentada o archivada.')
    motivo = str(motivo or '').strip()
    _exigir(motivo, 'Escribe por qué se rechaza.')
    ahora = datetime.utcnow()
    for item in sol.items:
        if item.estado == 'APROBADO':
            item.estado, item.motivo_rechazo, item.revisado_por, item.revisado_en = 'RECHAZADO', motivo, usuario, ahora
    desde = {'ARCHIVADO': 'archivada', 'POR_DEVOLVER': 'por devolver', 'DEPOSITADO': 'con ítems aprobados'}.get(sol.estado, 'sustentada')
    sol.estado, sol.archivado_en = 'DEPOSITADO', None
    _historial(sol, 'rechazar %s: vuelve a Por rendir' % desde, usuario, motivo)
    db.session.commit()


# ── Vistas ─────────────────────────────────────────────────────────────────

def montos_etapa(sol):
    """Importes por etapa sin repetir el depósito completo."""
    if sol.estado in ('PENDIENTE', 'RECHAZADO'):
        return {'validacion': sol.total}
    if sol.estado == 'VALIDADO':
        return {'deposito': sol.total}
    if sol.estado == 'ANULADO':
        return {'anuladas': sol.total}
    montos = {}
    for item in sol.items:
        if sol.estado == 'ARCHIVADO' and item.estado != 'APROBADO':
            continue  # archivada: solo cuenta lo aprobado
        if item.estado in ('POR_RENDIR', 'RECHAZADO'):
            vista, monto = 'por_rendir', item.monto
        elif item.estado == 'EN_REVISION':
            vista, monto = 'revision', item.monto_gastado or Decimal('0')
        elif item.estado == 'APROBADO':
            # Lo aprobado espera en Sustento hasta que la gestión archiva la solicitud.
            vista, monto = 'archivado' if sol.estado == 'ARCHIVADO' else 'sustento', item.monto_gastado or Decimal('0')
        else:
            continue
        montos[vista] = montos.get(vista, Decimal('0')) + monto
    if sol.estado == 'POR_DEVOLVER':
        vista = 'revision' if sol.devolucion_foto else 'por_rendir'
        montos[vista] = montos.get(vista, Decimal('0')) + max(Decimal('0'), diferencia(sol))
    if sol.estado == 'ARCHIVADO':
        montos.setdefault('archivado', Decimal('0'))
    if sol.estado == 'SUSTENTO':
        montos.setdefault('sustento', Decimal('0'))
    return montos


def etapa(sol):
    return set(montos_etapa(sol))


def retorno(sol):
    """Por qué una solicitud está otra vez en una etapa anterior ('' si va en orden)."""
    if sol.estado == 'RECHAZADO':
        return 'con_tecnico'
    if sol.estado == 'PENDIENTE':
        if sol.motivo_rechazo:
            return 'desde_deposito'
        ultimo = (json.loads(sol.historial or '[]') or [{}])[-1]
        if ultimo.get('accion') == 'reenviar':
            return 'reenviada'
    return ''


def comprobantes_de(item):
    """Comprobantes del ítem; lo rendido antes de esta función se ve como un solo comprobante."""
    if item.comprobantes:
        return json.loads(item.comprobantes)
    if not item.comprobante:
        return []
    return [{'ruc': item.ruc or '', 'razon_social': item.razon_social or '', 'comprobante': item.comprobante,
             'monto': dinero(item.monto_gastado) if item.monto_gastado is not None else '',
             'fotos': json.loads(item.fotos or '[]')}]


def revision_guardada(historial):
    return next((evento['revision'] for evento in reversed(historial) if 'revision' in evento), {})


def a_dict(sol, gestion=False):
    montos = montos_etapa(sol)
    historial = json.loads(sol.historial or '[]')
    conceptos = next((evento['conceptos'] for evento in reversed(historial) if 'conceptos' in evento), {})
    formulario = next((e['formulario'] for e in reversed(historial) if 'formulario' in e), {})
    # Pestaña extra "CM / Site pendiente": se suma a la etapa normal, no la reemplaza.
    faltan = datos_pendientes(sol, formulario)
    if faltan:
        montos = dict(montos, pendientes=sol.total)
    revision = {}
    envio = None
    if gestion:
        revision = revision_guardada(historial)
        for evento in reversed(historial):
            if evento['accion'] in ('solicitar', 'reenviar'):
                break
            if 'envio_tecnico' in evento:
                envio = evento['envio_tecnico']
                break
    return {
        'retorno': retorno(sol),
        'id': sol.id, 'codigo': sol.codigo, 'documento': sol.documento, 'tecnico': sol.tecnico,
        'proyecto': sol.proyecto, 'motivo': sol.motivo, 'banco': sol.banco, 'cuenta': sol.cuenta,
        'estado': sol.estado, 'etapas': sorted(montos), 'total': dinero(sol.total),
        'montos_etapa': {vista: dinero(monto) for vista, monto in montos.items()},
        'creado': sol.creado.isoformat(timespec='minutes'), 'motivo_rechazo': sol.motivo_rechazo or '',
        'deposito_fecha': sol.deposito_fecha or '', 'deposito_foto': sol.deposito_foto or '',
        'deposito_comentario': next((e.get('motivo') or '' for e in reversed(historial) if e.get('accion') == 'depositar'), ''),
        'depositado_en': sol.depositado_en.isoformat(timespec='minutes') if sol.depositado_en else '',
        'archivado_en': sol.archivado_en.isoformat(timespec='minutes') if sol.archivado_en else '',
        'validado_por': sol.validado_por or '',
        'deposito_monto': dinero(sol.deposito_monto) if sol.deposito_monto is not None else '',
        'depositado_por': sol.depositado_por or '',
        'diferencia': dinero(diferencia(sol)) if sol.deposito_monto is not None else '',
        'devolucion_foto': sol.devolucion_foto or '',
        'devolucion_monto': dinero(sol.devolucion_monto) if sol.devolucion_monto is not None else '',
        'devolucion_aceptada': bool(sol.devolucion_aceptada),
        'puede_devolver': puede_devolver(sol),
        'pendiente': dinero(sum(i.monto for i in sol.items if i.estado in ('POR_RENDIR', 'RECHAZADO'))) if sol.estado == 'DEPOSITADO' else '0.00',
        'avance': '%d de %d ítems aprobados' % (sum(i.estado == 'APROBADO' for i in sol.items), len(sol.items)),
        'items': [{'id': i.id, 'numero': i.numero, 'tipo_gasto': i.tipo_gasto, 'descripcion': i.descripcion,
                   'monto': dinero(i.monto), 'estado': i.estado, 'ruc': i.ruc or '', 'comprobante': i.comprobante or '',
                   'razon_social': i.razon_social or '', 'evidencia': i.evidencia or '',
                   'monto_gastado': dinero(i.monto_gastado) if i.monto_gastado is not None else '',
                   'fotos': json.loads(i.fotos or '[]'), 'motivo_rechazo': i.motivo_rechazo or '',
                   'comprobantes': comprobantes_de(i),
                   'evidencias': json.loads(i.evidencias or 'null') or ([i.evidencia] if i.evidencia else []),
                   'rendido_en': i.rendido_en.isoformat(timespec='minutes') if i.rendido_en else '',
                   'revisado_en': i.revisado_en.isoformat(timespec='minutes') if i.revisado_en else '',
                   'revisado_por': i.revisado_por or '',
                   # Última corrección de monto hecha al revisar (el técnico ve el porqué).
                   'correccion': next((e.get('motivo') or '' for e in reversed(historial)
                                       if e.get('accion') == 'corregir monto ítem %d' % i.numero), ''),
                   **conceptos.get(str(i.numero), {})}
                  for i in sol.items],
        'formulario': formulario,
        'faltan': faltan,
        'historial': [{k: v for k, v in evento.items() if k not in ('conceptos', 'revision', 'envio_tecnico', 'formulario')} for evento in historial],
        **({'revision': revision, 'envio_tecnico': envio} if gestion else {}),
    }


ESTADO_SOLICITUD = {'PENDIENTE': 'Pendiente', 'RECHAZADO': 'Devuelta al técnico', 'VALIDADO': 'Validada',
                    'DEPOSITADO': 'Depositada', 'POR_DEVOLVER': 'Por devolver', 'SUSTENTO': 'Sustentada', 'ARCHIVADO': 'Archivada'}
ESTADO_RENDICION = {'EN_REVISION': 'En revisión', 'RECHAZADO': 'Rechazado', 'POR_RENDIR': 'Por rendir', 'DEVUELTO': 'Devuelto'}
PESTANAS = {'validacion': 'Validación', 'deposito': 'Depósito', 'por_rendir': 'Por rendir', 'revision': 'Revisión',
            'sustento': 'Sustentado', 'archivado': 'Archivado', 'anuladas': 'Anuladas'}


def pestana_item(sol, item):
    """Pestaña de Caja chica donde está hoy cada ítem (la misma regla que reparte los montos por etapa)."""
    if sol.estado in ('PENDIENTE', 'RECHAZADO'):
        return PESTANAS['validacion']
    if sol.estado == 'VALIDADO':
        return PESTANAS['deposito']
    if sol.estado == 'ANULADO':
        return PESTANAS['anuladas']
    if item.estado in ('POR_RENDIR', 'RECHAZADO'):
        return PESTANAS['por_rendir']
    if item.estado == 'EN_REVISION':
        return PESTANAS['revision']
    if sol.estado == 'ARCHIVADO':
        return PESTANAS['archivado']
    if item.estado in ('APROBADO', 'DEVUELTO') and sol.estado == 'SUSTENTO':
        return PESTANAS['sustento']
    if item.estado == 'DEVUELTO':
        # Ítem devuelto: espera la captura (Por rendir) o su revisión (Revisión).
        return PESTANAS['revision' if sol.devolucion_foto and not sol.devolucion_aceptada else 'por_rendir']
    return PESTANAS['sustento']


def exportar_excel(solicitudes, dataper=None):
    """Historial plano: una fila por ítem, lista para tablas dinámicas (Depositado = Gastado + Devuelto al cerrar)."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Historial'
    hoja.append(['Código', 'Fecha solicitud', 'Proyecto', 'Site', 'N.º CM/PM/PLM', 'N.º cotización',
                 'Técnico', 'DNI', 'Supervisor', 'Registrado en Dataper', 'Departamento (Dataper)', 'Estado de solicitud', 'Concepto', 'Tipo de gasto', 'Justificación', 'Solicitado', 'Depositado',
                 'Fecha depósito', 'Gastado', 'Devuelto', 'Estado de rendición', 'Motivo de rechazo', 'Fecha rendición',
                 'Tiempo de rendición', 'Plazo 24 h', 'RUC', 'Razón social', 'N.º boleta'])
    cero = Decimal('0')
    peru = lambda f: (f - timedelta(hours=5)).replace(second=0, microsecond=0) if f else None  # las fechas se guardan en UTC
    pendientes = []
    for solicitud in solicitudes:
        datos = a_dict(solicitud, gestion=True)
        formulario = datos['formulario']
        if datos['faltan']:
            pendientes.append([formulario.get('responsable_validacion') or solicitud.validado_por or '', solicitud.codigo,
                               peru(solicitud.creado), solicitud.proyecto, solicitud.tecnico, solicitud.documento,
                               formulario.get('wo') or '', formulario.get('site') or '', ' y '.join(datos['faltan']),
                               ESTADO_SOLICITUD.get(solicitud.estado, solicitud.estado), solicitud.total])
        cotizacion = (datos.get('revision') or {}).get('cotizacion') or ''
        info = (dataper or {}).get(re.sub(r'[\s.\-]', '', solicitud.documento or '').upper(), {})
        supervisor = info.get('supervisor') or formulario.get('supervisor') or ''
        registrado = 'Registrado' if info.get('registrado') else 'No registrado'
        tipos = {i['id']: i.get('tipo_presupuesto') or '' for i in datos['items']}
        fecha = peru(solicitud.creado)
        depositada = solicitud.deposito_monto is not None
        # El depósito se reparte por ítem según lo solicitado; el último ítem absorbe el redondeo.
        repartido, por_item = cero, {}
        for n, item in enumerate(solicitud.items):
            if not depositada:
                por_item[item.id] = cero
            elif n == len(solicitud.items) - 1:
                por_item[item.id] = solicitud.deposito_monto - repartido
            else:
                por_item[item.id] = (solicitud.deposito_monto * item.monto / solicitud.total).quantize(Decimal('0.01')) if solicitud.total else cero
                repartido += por_item[item.id]
        for item in solicitud.items:
            rendido = item.estado in ('APROBADO', 'EN_REVISION')
            gastado = (item.monto_gastado or cero) if rendido else cero
            devuelto = item.monto if item.estado == 'DEVUELTO' else (item.monto - gastado if rendido else cero)
            if not depositada:
                estado_rendicion = 'Sin depósito'
            elif item.estado == 'APROBADO':
                estado_rendicion = 'Rendido con saldo' if devuelto > 0 else 'Rendido'
            else:
                estado_rendicion = ESTADO_RENDICION.get(item.estado, item.estado)
            rendicion = item.rendido_en if rendido else None
            # Plazo: rendir dentro de 24 h desde el depósito. Si aún no rinde, se compara con la hora actual.
            plazo = ''
            if solicitud.depositado_en and (rendicion or item.estado in ('POR_RENDIR', 'RECHAZADO')):
                horas = ((rendicion or datetime.utcnow()) - solicitud.depositado_en).total_seconds() / 3600
                plazo = 'Fuera de plazo' if horas > 24 else 'Dentro de plazo' if rendicion else ''
            # SLA: desde el depósito hasta la rendición, en días y horas.
            total = ''
            if rendicion and solicitud.depositado_en:
                horas_total = int((rendicion - solicitud.depositado_en).total_seconds() // 3600)
                total = ('%d d %d h' % divmod(horas_total, 24)) if horas_total >= 24 else '%d h' % horas_total
            comps = comprobantes_de(item)
            fila = [solicitud.codigo, fecha, solicitud.proyecto,
                    formulario.get('site') or '', formulario.get('wo') or '', cotizacion, solicitud.tecnico, solicitud.documento,
                    supervisor, registrado, info.get('departamento') or '', pestana_item(solicitud, item), item.tipo_gasto, tipos.get(item.id, ''), solicitud.motivo or '',
                    item.monto, por_item[item.id], peru(solicitud.depositado_en), gastado, devuelto,
                    estado_rendicion, item.motivo_rechazo or solicitud.motivo_rechazo or '', peru(rendicion), total, plazo,
                    *(' / '.join(dict.fromkeys(str(c.get(k) or '') for c in comps if c.get(k))) for k in ('ruc', 'razon_social', 'comprobante'))]
            hoja.append([ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v for v in fila])
            for celda in hoja[hoja.max_row]:
                if isinstance(celda.value, Decimal):
                    celda.number_format = '#,##0.00'
                elif isinstance(celda.value, datetime):
                    celda.number_format = 'DD/MM/YYYY HH:MM'
                elif isinstance(celda.value, str):
                    celda.data_type = 's'
    otra = libro.create_sheet('CM-Site pendiente')
    otra.append(['Responsable de validación', 'Código', 'Fecha solicitud', 'Proyecto', 'Técnico', 'DNI',
                 'N.º CM/PM/PLM', 'Site', 'Falta', 'Estado de solicitud', 'Total'])
    for fila in sorted(pendientes, key=lambda f: (f[0].lower(), f[2] or datetime.min)):
        otra.append([ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v for v in fila])
        otra.cell(otra.max_row, 3).number_format = 'DD/MM/YYYY HH:MM'
        otra.cell(otra.max_row, 11).number_format = '#,##0.00'
    for h in (hoja, otra):
        h.freeze_panes = 'A2'
        h.auto_filter.ref = h.dimensions
        for columna in h.columns:
            titulo = columna[0]
            titulo.font = Font(bold=True, color='FFFFFF')
            titulo.fill = PatternFill('solid', fgColor='B45309' if h is otra else '166534')
            h.column_dimensions[get_column_letter(titulo.column)].width = min(40, max(8, *(len(str(c.value or '')) + 2 for c in columna)))
    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    return archivo


# ── Fotos: B2 si está configurado; si no, disco local (desarrollo) ─────────

def _carpeta_local(sol):
    return os.path.join(current_app.config['EVIDENCIA_DIR'], 'caja_chica', str(sol.id))


def guardar_correo(sol, archivo):
    from services.apoyo import disco_efimero_sin_b2
    _exigir(not disco_efimero_sin_b2(), 'El almacenamiento de adjuntos no está configurado.')
    extension = os.path.splitext(archivo.filename)[1].lower()
    if extension in ('.jpg', '.jpeg', '.png', '.webp'):
        return guardar_foto(sol, archivo)
    _exigir(extension in ('.pdf', '.eml', '.msg'), 'Adjunta un PDF, correo .eml/.msg o una imagen.')
    limite = 10 * 1024 * 1024
    contenido = archivo.read(limite + 1)
    _exigir(0 < len(contenido) <= limite, 'El adjunto debe pesar hasta 10 MB.')
    _exigir(extension != '.pdf' or contenido.startswith(b'%PDF-'), 'El PDF no es válido.')
    nombre = uuid.uuid4().hex + extension
    _guardar_adjunto(sol, nombre, io.BytesIO(contenido))
    return nombre


def guardar_foto(sol, archivo):
    from services.apoyo import disco_efimero_sin_b2
    if disco_efimero_sin_b2():
        raise ValueError('El almacenamiento de fotos no está configurado. Avisa al administrador.')
    contenido = archivo.read(20 * 1024 * 1024 + 1)
    _exigir(len(contenido) <= 20 * 1024 * 1024, 'Cada foto debe pesar como máximo 20 MB.')
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen = ImageOps.exif_transpose(imagen).convert('RGB')
            imagen.thumbnail((1800, 1800))
            salida = io.BytesIO()
            imagen.save(salida, 'JPEG', quality=85)
    except Exception:
        raise ValueError('El archivo no es una imagen válida.') from None
    nombre = uuid.uuid4().hex + '.jpg'
    _guardar_adjunto(sol, nombre, salida)
    return nombre


def _guardar_adjunto(sol, nombre, salida):
    from services.apoyo import b2_cliente, evidencia_usa_b2
    if evidencia_usa_b2():
        salida.seek(0)
        b2_cliente().upload_fileobj(salida, current_app.config['B2_BUCKET'], 'caja-chica/%d/%s' % (sol.id, nombre))
    else:
        os.makedirs(_carpeta_local(sol), exist_ok=True)
        with open(os.path.join(_carpeta_local(sol), nombre), 'wb') as destino:
            destino.write(salida.getvalue())


def leer_foto(sol, nombre):
    from services.apoyo import b2_cliente, evidencia_usa_b2
    if evidencia_usa_b2():
        objeto = b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'], Key='caja-chica/%d/%s' % (sol.id, nombre))
        return objeto['Body'].read()
    with open(os.path.join(_carpeta_local(sol), nombre), 'rb') as origen:
        return origen.read()


def fotos_rendicion(sol):
    """Fotos del registro de Rendición del que se migró la solicitud (mismo CODIGO DEPOSITO).

    Devuelve [{'etiqueta', 'nombre'}] para fotos guardadas por Nucleus (se sirven como
    'ren~pid~clave~archivo') y [{'etiqueta', 'url'}] para enlaces externos (formulario)."""
    from models import NucleusData
    from urllib.parse import unquote, urlparse
    modulo = Proyecto.query.filter_by(nombre='Rendicion').first()
    if not modulo or not sol.codigo:
        return []
    candidatas = NucleusData.query.filter(NucleusData.proyecto_id == modulo.id,
                                          NucleusData.data_json.like('%' + sol.codigo + '%')).limit(20).all()
    fila = None
    for c in candidatas:
        try:
            datos = json.loads(c.data_json or '{}')
        except ValueError:
            continue
        if str(datos.get('CODIGO DEPOSITO') or '').strip().upper() == sol.codigo.upper():
            fila = (c, datos)
            break
    if not fila:
        return []
    registro, datos = fila
    fotos, vistas = [], set()

    def agregar(etiqueta, valor):
        texto = str(valor or '').replace('\\/', '/')
        urls = re.findall(r"""(?:https?://[^\s,;"'<>\]]+|/(?:api|static)/[^\s,;"'<>\]]+)""", texto)
        for n, url in enumerate(urls, 1):
            if url in vistas:
                continue
            vistas.add(url)
            nombre_foto = etiqueta + (' %d' % n if len(urls) > 1 else '')
            ruta = urlparse(url).path if url.startswith('/') else ''
            partes = ruta.split('/')
            if ruta.startswith('/api/rendicion/foto/') and len(partes) >= 7:
                # /api/rendicion/foto/<pid>/<clave>/<archivo>
                fotos.append({'etiqueta': nombre_foto,
                              'nombre': 'ren~%s~%s~%s' % (partes[4], unquote(partes[5]), unquote(partes[6]))})
            elif url.startswith('http'):
                fotos.append({'etiqueta': nombre_foto, 'url': url})
    agregar('Foto de sustento', datos.get('FOTOS SUSTENTO'))
    for clave, valor in datos.items():
        if str(clave).upper().startswith('SUSTENTO_') and str(clave).upper() != 'SUSTENTO_MARCAS':
            etiqueta = str(clave)[9:].strip()
            if etiqueta.upper().startswith('FOTO '):
                etiqueta = etiqueta[5:].strip()
            agregar(etiqueta.capitalize() or 'Sustento', valor)
    return fotos


def fotos_de(sol):
    nombres = {sol.deposito_foto, sol.devolucion_foto}
    for item in sol.items:
        nombres.update(json.loads(item.fotos or '[]'))
        nombres.update(json.loads(item.evidencias or '[]'))
        nombres.add(item.evidencia)
    return {n for n in nombres if n}
