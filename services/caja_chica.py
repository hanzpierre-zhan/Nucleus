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
ESTADOS_FINALES = ('ARCHIVADO', 'ANULADO')


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
    columnas = {c['name'] for c in inspect(db.engine).get_columns('caja_chica_items')}
    for nombre, tipo in (('razon_social', 'VARCHAR(200)'), ('evidencia', 'VARCHAR(120)')):
        if nombre not in columnas:
            db.session.execute(db.text('ALTER TABLE caja_chica_items ADD COLUMN %s %s' % (nombre, tipo)))
            db.session.commit()


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
                         'correo': fila.get('correo') is True, 'cotizacion': fila.get('cotizacion') is True})
    return catalogo


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
    _exigir(isinstance(items, list) and 1 <= len(items) <= MAX_ITEMS, 'Agrega entre 1 y %d ítems.' % MAX_ITEMS)
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
            regla = disponibles[tipo]
        correo = str(item.get('correo_validador') or '').strip() if regla['correo'] else ''
        _exigir(not regla['correo'] or (len(correo) <= 254 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo)),
                'Ítem %d: ingresa el correo de quien valida el gasto.' % n)
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


def datos_formulario(datos, supervisor, responsables):
    campos = {'site': 150, 'wo': 100, 'titular': 150}
    formulario = {campo: str(datos.get(campo) or '').strip() for campo in campos}
    _exigir(all(len(formulario[c]) <= limite for c, limite in campos.items()), 'Revisa la longitud de los datos de la solicitud.')
    billetera = str(datos.get('tipo_billetera') or 'No aplica')
    _exigir(billetera in ('No aplica', 'Yape', 'Plin'), 'Selecciona una billetera válida.')
    numero = str(datos.get('numero_billetera') or '').strip() if billetera != 'No aplica' else ''
    _exigir(billetera == 'No aplica' or re.fullmatch(r'[0-9]{9}', numero), 'Ingresa los 9 dígitos de Yape o Plin.')
    responsable_id = str(datos.get('responsable_validacion') or '')
    responsable = responsables.get(responsable_id, '')
    _exigir(not responsable_id or responsable, 'Selecciona un responsable asignado al proyecto.')
    return dict(formulario, supervisor=supervisor, tipo_billetera=billetera, numero_billetera=numero,
                responsable_validacion=responsable, responsable_validacion_id=responsable_id)


def crear(tecnico, datos, catalogo, proyectos, bancos, importe, formulario=None):
    sol = CajaChicaSolicitud(documento=tecnico['documento'], tecnico=tecnico['nombre'], estado='PENDIENTE')
    conceptos = _llenar(sol, datos, catalogo, proyectos, bancos, importe)
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


def rendir_item(sol, item, documento, datos, fotos, importe, evidencia=None):
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(sol.estado == 'DEPOSITADO', 'Solo se rinde una solicitud depositada.')
    _exigir(item.estado in ('POR_RENDIR', 'RECHAZADO'), 'Este ítem ya fue rendido.')
    ruc = re.sub(r'\D', '', str(datos.get('ruc') or ''))
    _exigir(len(ruc) == 11, 'Escribe el RUC del comprobante (11 dígitos).')
    comprobante = str(datos.get('comprobante') or '').strip().upper()
    _exigir(re.fullmatch(r'[A-Z0-9-]{3,40}', comprobante), 'Escribe el número de la boleta o factura.')
    gastado = importe(datos.get('monto_gastado'))
    _exigir(gastado <= item.monto, 'El monto gastado no puede superar el monto del ítem (S/ %s).' % dinero(item.monto))
    _exigir(1 <= len(fotos) <= MAX_FOTOS, 'Adjunta entre 1 y %d fotos del comprobante.' % MAX_FOTOS)
    _exigir(evidencia, 'Adjunta la foto de la evidencia del gasto.')
    item.ruc, item.comprobante, item.monto_gastado = ruc, comprobante, gastado
    # La razón social la completa el portal con la consulta de RUC; solo se guarda como referencia.
    item.razon_social = str(datos.get('razon_social') or '').strip()[:200] or None
    item.fotos, item.evidencia = json.dumps(fotos), evidencia
    item.estado, item.rendido_en, item.motivo_rechazo = 'EN_REVISION', datetime.utcnow(), None
    _historial(sol, 'rendir ítem %d' % item.numero, sol.tecnico)
    db.session.commit()


def devolver_item(sol, item, documento):
    """El técnico no puede sustentar un ítem rechazado: su monto pasa a la devolución."""
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(sol.estado == 'DEPOSITADO' and item.estado == 'RECHAZADO', 'Solo se devuelve un ítem rechazado.')
    item.estado, item.monto_gastado = 'DEVUELTO', Decimal('0')
    _historial(sol, 'devolver ítem %d' % item.numero, sol.tecnico)
    _cerrar_si_resuelto(sol, sol.tecnico)
    db.session.commit()


def devolver(sol, documento, monto, foto, importe):
    _exigir(sol.documento == documento, 'Esta solicitud no es tuya.')
    _exigir(sol.estado == 'POR_DEVOLVER' and not sol.devolucion_foto, 'No hay devolución pendiente.')
    _exigir(importe(monto) == diferencia(sol), 'La devolución debe ser exactamente S/ %s.' % dinero(diferencia(sol)))
    sol.devolucion_monto, sol.devolucion_foto = diferencia(sol), foto
    _historial(sol, 'registrar devolución', sol.tecnico)
    db.session.commit()


# ── Gestión (Nucleus) ──────────────────────────────────────────────────────

def validar(sol, usuario):
    _exigir(sol.estado == 'PENDIENTE', 'Solo se valida una solicitud pendiente.')
    datos = a_dict(sol, gestion=True)
    revision = datos['revision']
    _exigir(not any(i.get('requiere_correo') for i in datos['items']) or revision.get('archivo'),
            'Abre el código de la solicitud y adjunta el correo de validación.')
    _exigir(not any(i.get('requiere_cotizacion') for i in datos['items']) or revision.get('cotizacion'),
            'Abre el código de la solicitud e ingresa el número de cotización.')
    sol.estado, sol.validado_por, sol.validado_en = 'VALIDADO', usuario, datetime.utcnow()
    sol.motivo_rechazo = None
    _historial(sol, 'validar', usuario)
    db.session.commit()


def _documentos_revision(sol, cotizacion, archivo, revision):
    cotizacion = str(cotizacion or '').strip()
    _exigir(len(cotizacion) <= 80, 'El número de cotización admite hasta 80 caracteres.')
    adjunto = revision.get('archivo', '')
    if archivo and archivo.filename:
        adjunto = guardar_correo(sol, archivo)
    return {'archivo': adjunto, 'cotizacion': cotizacion}


def guardar_documentos_revision(sol, usuario, cotizacion, archivo):
    _exigir(sol.estado == 'PENDIENTE', 'Solo se pueden guardar documentos mientras la solicitud esté pendiente.')
    anterior = a_dict(sol, gestion=True)['revision']
    revision = _documentos_revision(sol, cotizacion, archivo, anterior)
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


def depositar(sol, usuario, monto, foto, importe):
    """La fecha y hora se registran solas al confirmar (no las escribe el usuario)."""
    _exigir(sol.estado == 'VALIDADO', 'Solo se deposita una solicitud validada.')
    _exigir(importe(monto) == sol.total, 'El depósito debe ser el total solicitado (S/ %s).' % dinero(sol.total))
    _exigir(foto, 'Adjunta la foto del depósito.')
    ahora = datetime.utcnow()
    sol.estado, sol.deposito_monto, sol.depositado_en = 'DEPOSITADO', sol.total, ahora
    sol.deposito_fecha = (ahora - timedelta(hours=5)).strftime('%Y-%m-%d')  # día en Lima (UTC-5)
    sol.deposito_foto, sol.depositado_por = foto, usuario
    _historial(sol, 'depositar', usuario)
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


def _cerrar_si_resuelto(sol, usuario):
    """Cuando ningún ítem queda por rendir, revisar o corregir: archiva o pide la devolución."""
    if all(i.estado in ('APROBADO', 'DEVUELTO') for i in sol.items):
        _cerrar_o_pedir_devolucion(sol, usuario)


def confirmar_devolucion(sol, usuario, aceptar, motivo=''):
    _exigir(sol.estado == 'POR_DEVOLVER' and sol.devolucion_foto, 'No hay devolución por revisar.')
    if aceptar:
        sol.estado, sol.archivado_en = 'ARCHIVADO', datetime.utcnow()
        _historial(sol, 'confirmar devolución y archivar', usuario)
    else:
        _exigir(str(motivo or '').strip(), 'Escribe por qué se rechaza la devolución.')
        sol.devolucion_monto = sol.devolucion_foto = None
        _historial(sol, 'rechazar devolución', usuario, motivo.strip())
    db.session.commit()


def diferencia(sol):
    gastado = sum((i.monto_gastado or Decimal('0') for i in sol.items), Decimal('0'))
    return (sol.deposito_monto or Decimal('0')) - gastado


def _cerrar_o_pedir_devolucion(sol, usuario):
    if diferencia(sol) > 0:
        sol.estado = 'POR_DEVOLVER'
        _historial(sol, 'ítems resueltos: falta la devolución', usuario)
    else:
        sol.estado, sol.archivado_en = 'ARCHIVADO', datetime.utcnow()
        _historial(sol, 'ítems resueltos: archivado', usuario)


# ── Vistas ─────────────────────────────────────────────────────────────────

def etapa(sol):
    """Pestañas de la gestión. Una solicitud depositada puede estar en las dos.
    Una rechazada en validación sigue visible en Validación mientras el técnico corrige."""
    if sol.estado in ('PENDIENTE', 'RECHAZADO'):
        return {'validacion'}
    if sol.estado == 'VALIDADO':
        return {'deposito'}
    # "Por rendir" lista todo lo ya depositado y aún no archivado; además aparece en
    # "Revisión" mientras tenga comprobantes o una devolución por revisar.
    if sol.estado == 'DEPOSITADO':
        return {'por_rendir'} | ({'revision'} if any(i.estado == 'EN_REVISION' for i in sol.items) else set())
    if sol.estado == 'POR_DEVOLVER':
        return {'por_rendir'} | ({'revision'} if sol.devolucion_foto else set())
    return {'archivado'} if sol.estado == 'ARCHIVADO' else {'anuladas'}


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


def revision_guardada(historial):
    return next((evento['revision'] for evento in reversed(historial) if 'revision' in evento), {})


def a_dict(sol, gestion=False):
    aprobados = sum(i.monto for i in sol.items if i.estado == 'APROBADO')
    historial = json.loads(sol.historial or '[]')
    conceptos = next((evento['conceptos'] for evento in reversed(historial) if 'conceptos' in evento), {})
    formulario = next((e['formulario'] for e in reversed(historial) if 'formulario' in e), {})
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
        'estado': sol.estado, 'etapas': sorted(etapa(sol)), 'total': dinero(sol.total),
        'creado': sol.creado.isoformat(timespec='minutes'), 'motivo_rechazo': sol.motivo_rechazo or '',
        'deposito_fecha': sol.deposito_fecha or '', 'deposito_foto': sol.deposito_foto or '',
        'depositado_en': sol.depositado_en.isoformat(timespec='minutes') if sol.depositado_en else '',
        'validado_por': sol.validado_por or '',
        'deposito_monto': dinero(sol.deposito_monto) if sol.deposito_monto is not None else '',
        'depositado_por': sol.depositado_por or '',
        'diferencia': dinero(diferencia(sol)) if sol.deposito_monto is not None else '',
        'devolucion_foto': sol.devolucion_foto or '',
        'pendiente': dinero(sol.total - aprobados) if sol.estado not in ESTADOS_FINALES else '0.00',
        'avance': '%d de %d ítems aprobados' % (sum(i.estado == 'APROBADO' for i in sol.items), len(sol.items)),
        'items': [{'id': i.id, 'numero': i.numero, 'tipo_gasto': i.tipo_gasto, 'descripcion': i.descripcion,
                   'monto': dinero(i.monto), 'estado': i.estado, 'ruc': i.ruc or '', 'comprobante': i.comprobante or '',
                   'razon_social': i.razon_social or '', 'evidencia': i.evidencia or '',
                   'monto_gastado': dinero(i.monto_gastado) if i.monto_gastado is not None else '',
                   'fotos': json.loads(i.fotos or '[]'), 'motivo_rechazo': i.motivo_rechazo or '',
                   **conceptos.get(str(i.numero), {})}
                  for i in sol.items],
        'formulario': formulario,
        'historial': [{k: v for k, v in evento.items() if k not in ('conceptos', 'revision', 'envio_tecnico', 'formulario')} for evento in historial],
        **({'revision': revision, 'envio_tecnico': envio} if gestion else {}),
    }


def exportar_excel(solicitudes):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    def agregar(hoja, valores):
        hoja.append([ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v for v in valores])
        for celda in hoja[hoja.max_row]:
            if isinstance(celda.value, str):
                celda.data_type = 's'
            elif isinstance(celda.value, Decimal):
                celda.number_format = '"S/ " #,##0.00'

    libro = Workbook()
    resumen = libro.active
    resumen.title = 'Solicitudes'
    detalle = libro.create_sheet('Conceptos')
    agregar(resumen, ['Código depósito', 'Técnico', 'Documento', 'Proyecto', 'Estado', 'Fecha de solicitud (Perú)',
                      'Motivo', 'Total solicitado', 'Monto depositado', 'Fecha de depósito', 'Avance'])
    agregar(detalle, ['Código depósito', 'Ítem', 'Concepto', 'Tipo de presupuesto', 'Descripción', 'Monto solicitado',
                      'Monto gastado', 'Estado', 'Correo de validación', 'RUC', 'Comprobante'])
    for solicitud in solicitudes:
        datos = a_dict(solicitud)
        fecha = (solicitud.creado - timedelta(hours=5)).strftime('%d/%m/%Y %H:%M')
        agregar(resumen, [solicitud.codigo, solicitud.tecnico, solicitud.documento, solicitud.proyecto,
                          solicitud.estado, fecha, solicitud.motivo, solicitud.total, solicitud.deposito_monto,
                          solicitud.deposito_fecha, datos['avance']])
        for item in datos['items']:
            agregar(detalle, [solicitud.codigo, item['numero'], item['tipo_gasto'], item.get('tipo_presupuesto'),
                              item['descripcion'], Decimal(item['monto']),
                              Decimal(item['monto_gastado']) if item['monto_gastado'] else None,
                              item['estado'], item.get('correo_validador'), item['ruc'], item['comprobante']])
    for hoja in libro.worksheets:
        hoja.freeze_panes = 'A2'
        hoja.auto_filter.ref = hoja.dimensions
        for columna in hoja.columns:
            titulo = columna[0]
            titulo.font = Font(bold=True, color='FFFFFF')
            titulo.fill = PatternFill('solid', fgColor='166534')
            hoja.column_dimensions[get_column_letter(titulo.column)].width = min(45, max(14, *(len(str(c.value or '')) + 2 for c in columna)))
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


def fotos_de(sol):
    nombres = {sol.deposito_foto, sol.devolucion_foto}
    for item in sol.items:
        nombres.update(json.loads(item.fotos or '[]'))
        nombres.add(item.evidencia)
    return {n for n in nombres if n}
