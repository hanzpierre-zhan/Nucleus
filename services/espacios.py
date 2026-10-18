"""Permisos y atribución de registros del piloto. Sin herencias de acceso FLM.

Los módulos siguen usando sus registros originales; el proyecto de negocio es
una dimensión independiente. Una atribución ambigua nunca concede visibilidad.
"""
import json
import re
from services.normalizacion import normalizar
from datetime import datetime

from flask import request, session
from db import db
from models import (Proyecto, Usuario, NucleusData, PerfilEspacio, AccesoEspacio,
                    ClasificacionEspacio, AuditoriaEspacio, RefacturableDetalle, ProyectoNegocio)

MODULOS = {
    'operacion': ('Operación FLM', None),
    'personal': ('Personal / Dataper', 'Dataper'),
    'materiales': ('Materiales', 'Material'),
    'combustible': ('Combustible', 'Combustible'),
    'sites': ('Sites', 'SITE'),
    'mapa_sites': ('Mapa de Sites', 'SITE'),
    'generadores': ('Generadores', 'Generadores'),
    'cotizaciones': ('Cotizaciones', 'Cotizaciones'),
    'rendicion': ('Rendición', 'Rendicion'),
    'liquidaciones': ('Liquidaciones', 'Cotizaciones'),
}
PROYECTOS = {'FLM - ENTEL': 'Entel', 'FLM - PEXT': 'Entel - Pext',
             'FLM - CLARO': 'Claro', 'FLM - INTEGRATEL': 'Integratel'}
ACCIONES = {'consultar', 'exportar', 'editar', 'validar', 'rechazar', 'anular',
            'depositar', 'sustentar', 'revertir', 'devolver', 'observar',
            'archivar', 'desarchivar'}
PROTEGIDOS = {'estado', 'estadocotizacion', 'codigodeposito', 'proyecto',
              'nombredelproyecto', 'cliente', 'tipoproyecto', 'marcatemporal',
              'fechapago', 'montopago', 'fotopago', 'generada', 'bloqueada'}
PROTEGIDOS |= {
    'interaccion', 'codigointerno', 'norden',
    'fechasustento', 'fecharechazo', 'rechazadopor', 'fechavalidacion',
    'validadopor', 'depositadopor', 'sustentadopor', 'editadopor',
    'rechazadodesde', 'vecesrechazado', 'devueltopor', 'fechadevolucion',
    'observadopor', 'fechaobservacion', 'archivadopor', 'fechaarchivo',
    'desarchivadopor', 'fechadesarchivo', 'anuladodesde', 'anuladopor', 'fechaanulacion'}


def perfiles_sugeridos():
    lectura = {m: ['consultar', 'exportar'] for m in MODULOS}
    gestion = {m: ['consultar', 'exportar', 'editar'] if m not in ('liquidaciones', 'mapa_sites')
               else ['consultar', 'exportar'] for m in MODULOS}
    supervisor = {m: list(a) for m, a in gestion.items()}
    supervisor['rendicion'] += ['validar', 'rechazar', 'observar', 'sustentar']
    return {
        'Consulta de todos los módulos': lectura,
        'Gestor de proyecto': gestion,
        'Contrata de proyecto': {m: ['consultar'] for m in MODULOS},
        'Supervisor de proyecto': supervisor,
        'Cotizaciones central': {'cotizaciones':['consultar','exportar','editar'],
                                 'liquidaciones':['consultar','exportar']},
        'Finanzas': {'rendicion':['consultar','exportar','depositar'],
                     'liquidaciones':['consultar','exportar']},
        'Certificación': {'liquidaciones':['consultar','exportar'],
                          'cotizaciones':['consultar','exportar']},
    }




def nombre_negocio(valor):
    fijo = {
        'entel': 'FLM - ENTEL', 'flmentel': 'FLM - ENTEL', 'flm': 'FLM - ENTEL',
        'entelpext': 'FLM - PEXT', 'flmentelpext': 'FLM - PEXT',
        'pext': 'FLM - PEXT', 'flmpext': 'FLM - PEXT',
        'claro': 'FLM - CLARO', 'flmclaro': 'FLM - CLARO',
        'integratel': 'FLM - INTEGRATEL', 'flmintegratel': 'FLM - INTEGRATEL',
    }.get(normalizar(valor))
    if fijo:
        return fijo
    if 'espacios.aliases' not in request.environ:
        alias = {}
        for p, negocio in db.session.query(Proyecto, ProyectoNegocio).join(
                ProyectoNegocio, Proyecto.id == ProyectoNegocio.proyecto_id).all():
            alias[normalizar(p.nombre)] = p.nombre
            alias[normalizar(negocio.nombre)] = p.nombre
        request.environ['espacios.aliases'] = alias
    return request.environ['espacios.aliases'].get(normalizar(valor))


def es_admin():
    usuario = db.session.get(Usuario, session.get('user_id'))
    return bool(usuario and usuario.rol in ('zeno', 'suport'))


def proyectos():
    extras = [p.proyecto_id for p in ProyectoNegocio.query.all()]
    from sqlalchemy import or_
    return Proyecto.query.filter(or_(Proyecto.nombre.in_(PROYECTOS), Proyecto.id.in_(extras))).order_by(Proyecto.nombre).all()


def etiquetas_proyectos():
    etiquetas = {p.id: PROYECTOS.get(p.nombre, p.nombre) for p in proyectos()}
    etiquetas.update({p.proyecto_id: p.nombre for p in ProyectoNegocio.query.all()})
    return etiquetas


def validar_permisos(valor):
    if not isinstance(valor, dict) or set(valor) - set(MODULOS):
        raise ValueError('Módulos inválidos.')
    resultado = {}
    for modulo, acciones in valor.items():
        if not isinstance(acciones, list) or any(not isinstance(a, str) for a in acciones):
            raise ValueError('Acciones inválidas.')
        permitidas = ACCIONES if modulo == 'rendicion' else {'consultar', 'exportar', 'editar'}
        if modulo in ('liquidaciones', 'mapa_sites'):
            permitidas = {'consultar', 'exportar'}
        if set(acciones) - permitidas or (acciones and 'consultar' not in acciones):
            raise ValueError('Toda acción requiere consultar; revisa las acciones del módulo.')
        if acciones:
            resultado[modulo] = sorted(set(acciones))
    return resultado


def permisos():
    """Se recalculan por solicitud: una revocación no depende de la cookie."""
    if 'espacios.permisos' in request.environ:
        return request.environ['espacios.permisos']
    if es_admin():
        resultado = {p.id: {m: sorted(ACCIONES if m == 'rendicion' else (
            {'consultar', 'exportar'} if m in ('liquidaciones', 'mapa_sites') else {'consultar', 'exportar', 'editar'}))
            for m in MODULOS} for p in proyectos()}
    else:
        resultado = {}
        for acceso, perfil in db.session.query(AccesoEspacio, PerfilEspacio).join(
                PerfilEspacio, AccesoEspacio.perfil_id == PerfilEspacio.id).filter(
                AccesoEspacio.usuario_id == session.get('user_id')).all():
            try:
                resultado[acceso.proyecto_id] = validar_permisos(json.loads(perfil.permisos_json))
            except (ValueError, TypeError):
                resultado[acceso.proyecto_id] = {}
    request.environ['espacios.permisos'] = resultado
    return resultado


def ids_permitidos(modulo, accion='consultar'):
    return {pid for pid, modulos in permisos().items() if accion in modulos.get(modulo, [])}


def auditar(accion, detalle):
    db.session.add(AuditoriaEspacio(usuario_id=session['user_id'], accion=accion,
                                    detalle_json=json.dumps(detalle, ensure_ascii=False)))


def _datos(fila):
    try:
        datos = json.loads(fila.data_json)
        return datos if isinstance(datos, dict) else {}
    except (ValueError, TypeError):
        return {}


def atribuciones():
    if 'espacios.atribuciones' in request.environ:
        return request.environ['espacios.atribuciones']
    negocios = {p.nombre: p.id for p in proyectos()}
    fuentes = {p.id: p.nombre for p in Proyecto.query.all()}
    filas = NucleusData.query.order_by(NucleusData.id).all()
    explicitas = {c.registro_id: c.proyecto_id for c in ClasificacionEspacio.query.all()}
    wo = {}
    for fila in filas:
        nombre = fuentes.get(fila.proyecto_id)
        if nombre in negocios:
            wo.setdefault(fila.key_value.strip().casefold(), set()).add(negocios[nombre])
    resultado = []
    for fila in filas:
        datos = _datos(fila)
        fuente = fuentes.get(fila.proyecto_id, '')
        if fuente in negocios:
            negocio = negocios[fuente]
        elif fila.id in explicitas:
            negocio = explicitas[fila.id] if explicitas[fila.id] in negocios.values() else None
        else:
            candidatos = set()
            for clave, valor in datos.items():
                if normalizar(clave) in ('proyecto', 'nombredelproyecto', 'tipoproyecto', 'tipodeproyecto', 'cliente'):
                    nombre = nombre_negocio(valor)
                    if nombre in negocios:
                        candidatos.add(negocios[nombre])
                if normalizar(clave) in ('numerowo', 'numerodewo', 'wonumber'):
                    for codigo in re.split(r'[,;\n]+', str(valor or '')):
                        candidatos.update(wo.get(codigo.strip().casefold(), set()))
            negocio = next(iter(candidatos)) if len(candidatos) == 1 else None
        resultado.append((fila, datos, fuente, negocio))
    request.environ['espacios.atribuciones'] = resultado
    return resultado


def fecha_orden(valor):
    texto = str(valor or '').strip()
    for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return datetime.min


def registros(modulo, seleccion=None, accion='consultar'):
    permitidos = ids_permitidos(modulo, accion)
    if seleccion is not None:
        permitidos &= {seleccion}
    fuente_esperada = MODULOS[modulo][1]
    nombres = etiquetas_proyectos()
    fuentes_operacion = {p.nombre for p in proyectos()}
    detalles = {d.origen_id: _datos(d) for d in RefacturableDetalle.query.all()} if modulo == 'liquidaciones' else {}
    salida = []
    incluir_sin_proyecto = es_admin() and seleccion is None and accion in ('consultar','exportar')
    for fila, datos, fuente, negocio in atribuciones():
        if negocio not in permitidos and not (negocio is None and incluir_sin_proyecto):
            continue
        if (modulo == 'operacion' and fuente not in fuentes_operacion) or (
                modulo != 'operacion' and fuente != fuente_esperada):
            continue
        if modulo == 'liquidaciones':
            from blueprints.refacturable import _ingresada
            if not _ingresada(datos):
                continue
            datos = {**datos, **{'Seguimiento · ' + k: v for k, v in detalles.get(fila.id, {}).items()}}
        visibles = {k: v for k, v in datos.items() if not k.startswith('_')}
        salida.append({'id': fila.id, 'clave': fila.key_value, 'proyecto_id': negocio,
                       'proyecto': nombres.get(negocio, 'Sin proyecto · pendiente de clasificar'), 'datos': visibles})
    salida.sort(key=lambda r: (fecha_orden(r['datos'].get('Marca temporal') or r['datos'].get('FECHA')),
                               r['id']), reverse=True)
    return salida
