"""Alcance de datos de las cuentas nativas, aplicado en servidor.

La asignación a un módulo permite usarlo; los proyectos asignados delimitan
sus registros. La política se aplica a consultas, exportaciones y escrituras.
"""
import json
from contextlib import contextmanager

from flask import abort, current_app, has_request_context, request, session
from sqlalchemy import JSON, and_, case, cast, event, exists, func, or_, select, true
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.sql import visitors

from db import db
from models import (AccesoProyecto, CuentaEspacio, Cotizacion, HistorialCambios,
                    NucleusData, NucleusHistory, Proyecto, RefacturableDetalle, Usuario)
from services.normalizacion import normalizar
from services.recursos_flm import familia

COMPARTIDOS = frozenset(('Dataper', 'Material', 'SITE', 'Site Name', 'Generadores',
                         'Combustible', 'Cotizaciones', 'Rendicion', 'Liquidaciones'))
CAMPOS = ('Nombre del proyecto', 'NOMBRE DEL PROYECTO', 'PROYECTO', 'CLIENTE',
          'Proyecto', 'TIPO PROYECTO', 'TIPO DE PROYECTO')
ALIAS = {'ENTEL': ('flm', 'entel', 'flmentel'),
         'CLARO': ('claro', 'flmclaro'),
         'INTEGRATEL': ('integratel', 'flmintegratel'),
         'PEXT': ('pext', 'flmpext', 'entelpext', 'flmentelpext')}


@contextmanager
def importacion_rendicion():
    """Trabajo global del importador, después de autorizar acceso al módulo.

    No concede permisos de edición/validación al usuario. Solo Rendición se
    escribe; Personal se consulta para el cruce por documento de la importación.
    El indicador es interno a la solicitud y siempre se restaura.
    """
    clave = 'nucleus.importacion_rendicion'
    anterior = request.environ.get(clave)
    request.environ[clave] = {p.nombre: p.id for p in Proyecto.query.filter(
        Proyecto.nombre.in_(('Rendicion', 'Dataper')))}
    try:
        yield
    finally:
        if anterior is None:
            request.environ.pop(clave, None)
        else:
            request.environ[clave] = anterior


@contextmanager
def vista_global():
    """Dashboards de Analytics: la data del módulo se muestra completa.

    Cotizaciones y Rendición son vistas de análisis compartidas por todos
    los usuarios; este indicador suspende el alcance por proyecto solo en
    las consultas de lectura de la solicitud actual. Las escrituras
    siguen validándose con el alcance normal.
    """
    clave = 'nucleus.vista_global'
    anterior = request.environ.get(clave)
    request.environ[clave] = True
    try:
        yield
    finally:
        if anterior is None:
            request.environ.pop(clave, None)
        else:
            request.environ[clave] = anterior


def contexto():
    if not has_request_context() or not session.get('user_id'):
        return None
    if 'nucleus.alcance' in request.environ:
        return request.environ['nucleus.alcance']
    usuario = db.session.get(Usuario, session['user_id'])
    if usuario is None:
        abort(401)
    piloto = current_app.config.get('ESPACIOS_HABILITADOS') and db.session.get(CuentaEspacio, session['user_id'])
    if piloto or (usuario and usuario.rol == 'zeno'):
        resultado = None
    else:
        proyectos = {p.id: p.nombre for p in Proyecto.query.all()}
        asignados = {a.proyecto_id for a in AccesoProyecto.query.filter_by(usuario_id=session['user_id'])}
        familias = {familia(proyectos.get(pid, '')) for pid in asignados} - {''}
        resultado = {'familias': familias, 'proyectos': proyectos,
                     'operacion': {pid for pid, n in proyectos.items() if familia(n) in familias},
                     'compartidos': {pid for pid, n in proyectos.items() if n in COMPARTIDOS}}
    request.environ['nucleus.alcance'] = resultado
    return resultado


def _valor(columna, clave):
    if db.engine.dialect.name == 'sqlite':
        return func.json_extract(columna, '$."' + clave + '"')
    return cast(columna, JSON)[clave].as_string()


def _familia_sql(valor):
    texto = func.lower(func.trim(func.coalesce(valor, '')))
    for separador in (' ', '-', '–', '—', '_'):
        texto = func.replace(texto, separador, '')
    return case({alias: nombre for nombre, valores in ALIAS.items() for alias in valores},
                value=texto, else_=None)


def _proyecto_sql(columna):
    return _familia_sql(_primero(columna, CAMPOS))


def _primero(columna, campos):
    return func.coalesce(*[func.nullif(func.trim(_valor(columna, k)), '') for k in campos], '')


def _qr_por_operacion(qr, ctx):
    """Proyectos del generador demostrados por sus movimientos asociados a WO."""
    t = NucleusData.__table__
    movimiento = t.alias('alcance_movimiento')
    fuente = t.alias('alcance_fuente_qr')
    combustible = [pid for pid, n in ctx['proyectos'].items() if n == 'Combustible']
    otros = [pid for pid, n in ctx['proyectos'].items() if familia(n) and pid not in ctx['operacion']]
    qr_mov = _primero(movimiento.c.data_json, ('QR ASIGNADO',))
    wo_mov = _primero(movimiento.c.data_json, ('WO NUMBER', 'NUMERO WO', 'N° WO NUMBER'))

    def codigos(pids):
        claves = select(fuente.c.key_value).where(fuente.c.proyecto_id.in_(pids))
        return select(qr_mov).where(movimiento.c.proyecto_id.in_(combustible), qr_mov != '', wo_mov.in_(claves))

    return and_(qr != '', qr.in_(codigos(ctx['operacion'])), ~qr.in_(codigos(otros)))


def _site_por_operacion(t, ctx):
    fuente = NucleusData.__table__.alias('alcance_fuente_site')
    nombre = func.lower(_primero(fuente.c.data_json, ('Nombre de Site', 'NOMBRE DE SITE', 'NOMBRE SITE', 'NOMBRE DEL SITE')))

    def codigo(valor):
        posicion = func.instr(valor, '_') if db.engine.dialect.name == 'sqlite' else func.strpos(valor, '_')
        return case((posicion > 0, func.substr(valor, 1, posicion - 1)), else_=valor)

    otros = [pid for pid, n in ctx['proyectos'].items() if familia(n) and pid not in ctx['operacion']]
    # Se reutilizan nombres/códigos en cuatro cruces. PostgreSQL materializa
    # esta CTE compartida y evita decodificar cada WO por cada site del maestro.
    base = select(fuente.c.proyecto_id, nombre.label('nombre'), codigo(nombre).label('codigo')).where(
        fuente.c.proyecto_id.in_(set(otros) | ctx['operacion'])).cte('alcance_sites_base')
    site = func.lower(_primero(t.c.data_json, ('NOMBRE DE SITE', 'Nombre de Site', 'Nombre', 'NOMBRE SITE')))
    cod = func.lower(_primero(t.c.data_json, ('Código', 'CODIGO', 'Código Site', 'CODIGO SITE')))

    def coincidencia(pids):
        nombres = select(base.c.nombre).where(base.c.proyecto_id.in_(pids), base.c.nombre != '')
        codigos = select(base.c.codigo).where(base.c.proyecto_id.in_(pids), base.c.codigo != '')
        return or_(and_(site != '', site.in_(nombres)), and_(cod != '', cod.in_(codigos)))

    return and_(t.c.proyecto_id.in_([pid for pid, n in ctx['proyectos'].items() if n in ('SITE', 'Site Name')]),
                coincidencia(ctx['operacion']), ~coincidencia(otros))


def criterio(tabla=None):
    ctx = contexto()
    if ctx is None:
        return None
    if set(ALIAS) <= ctx['familias']:
        return true()
    t = NucleusData.__table__ if tabla is None else tabla
    proyecto = _proyecto_sql(t.c.data_json)
    # Las filas sin proyecto explícito solo se atribuyen por una WO inequívoca.
    wo = NucleusData.__table__.alias('alcance_wo')
    claves = [_valor(t.c.data_json, k) for k in ('NUMERO WO', 'NUMERO DE WO', 'N° WO NUMBER', 'WO NUMBER', 'Número de WO')]
    coincide = or_(*[wo.c.key_value == k for k in claves])
    operativos = [pid for pid, nombre in ctx['proyectos'].items() if familia(nombre)]
    vinculo = and_(
        t.c.proyecto_id.in_([pid for pid, n in ctx['proyectos'].items() if n in ('Combustible', 'Cotizaciones', 'Rendicion')]),
        func.coalesce(*claves, '') != '',
        exists(select(1).select_from(wo).where(coincide, wo.c.proyecto_id.in_(ctx['operacion']))),
        ~exists(select(1).select_from(wo).where(coincide, wo.c.proyecto_id.in_(set(operativos) - ctx['operacion']))))
    # Los ingresos de combustible pueden no tener WO: el QR del generador
    # aporta el proyecto, siempre que no haya una atribución contradictoria.
    generadores = [pid for pid, n in ctx['proyectos'].items() if n == 'Generadores']
    gen = NucleusData.__table__.alias('alcance_generador')
    qr = _valor(t.c.data_json, 'QR ASIGNADO')
    coincide_gen = and_(gen.c.proyecto_id.in_(generadores), qr.is_not(None), qr != '',
                       or_(gen.c.key_value == qr, _valor(gen.c.data_json, 'QR ASIGNADO') == qr))
    familia_gen = _proyecto_sql(gen.c.data_json)
    vinculo_gen = and_(
        t.c.proyecto_id.in_([pid for pid, n in ctx['proyectos'].items() if n == 'Combustible']),
        exists(select(1).select_from(gen).where(coincide_gen, familia_gen.in_(ctx['familias']))),
        ~exists(select(1).select_from(gen).where(coincide_gen,
            or_(familia_gen.is_(None), ~familia_gen.in_(ctx['familias'])))))
    por_qr = and_(t.c.proyecto_id.in_([pid for pid, n in ctx['proyectos'].items() if n in ('Generadores', 'Combustible')]),
                  _qr_por_operacion(_primero(t.c.data_json, ('QR ASIGNADO',)), ctx))
    compartido = and_(t.c.proyecto_id.in_(ctx['compartidos']),
                     or_(proyecto.in_(ctx['familias']), and_(proyecto.is_(None),
                         or_(vinculo, vinculo_gen, por_qr, _site_por_operacion(t, ctx)))))
    conocidos = set(operativos) | ctx['compartidos']
    importacion = request.environ.get('nucleus.importacion_rendicion', {})
    return or_(t.c.proyecto_id.in_(ctx['operacion']), compartido,
               ~t.c.proyecto_id.in_(conocidos), t.c.proyecto_id.in_(importacion.values()))


def limitar_opciones(columnas):
    ctx = contexto()
    if ctx is None:
        return columnas
    resultado = []
    for columna in columnas:
        c = dict(columna)
        if normalizar(c.get('nombre', '')) in {normalizar(k) for k in CAMPOS}:
            c['opciones'] = [v for v in c.get('opciones', []) if familia(v) in ctx['familias']]
        resultado.append(c)
    return resultado


def _consultas(estado):
    if not has_request_context() or not session.get('user_id'):
        return
    if request.environ.get('nucleus.vista_global'):
        return
    modelos = {m.class_ for m in estado.all_mappers}
    # Query.count() envuelve el SELECT ORM en una subconsulta y no expone
    # all_mappers; conserva sus anotaciones en los nodos interiores.
    for nodo in visitors.iterate(estado.statement):
        mapper = nodo._annotations.get('parentmapper')
        if mapper is not None:
            modelos.add(mapper.class_)
    protegidos = {NucleusData, NucleusHistory, HistorialCambios, Cotizacion, RefacturableDetalle}
    if not modelos & protegidos:
        return
    restriccion = criterio()
    if restriccion is not None:
        for modelo in modelos & protegidos:
            if modelo is NucleusData:
                condicion = restriccion
            else:
                t = NucleusData.__table__
                enlace = (t.c.id == modelo.origen_id) if modelo is RefacturableDetalle else and_(
                    t.c.proyecto_id == modelo.proyecto_id, t.c.key_value == modelo.key_value)
                condicion = exists(select(1).select_from(t).where(enlace, restriccion).correlate_except(t))
            estado.statement = estado.statement.options(with_loader_criteria(modelo, condicion, include_aliases=True))


def comprobar_archivo(pid, key):
    """Protege también descargas por URL y fotos con la carpeta WO original."""
    if contexto() is None:
        return
    prefijos = ['/api/evidencia/foto/%s/%s/' % (pid, key),
                '/api/rendicion/foto/%s/%s/' % (pid, key),
                '/api/cotizacion/correo/%s/%s/' % (pid, key)]
    encontrado = NucleusData.query.filter(NucleusData.proyecto_id == pid, or_(
        NucleusData.key_value == key,
        *[NucleusData.data_json.contains(p, autoescape=True) for p in prefijos])).first()
    if not encontrado:
        from werkzeug.utils import secure_filename
        # Las URLs usan la clave saneada; la base conserva la original.
        permitido = any(secure_filename(str(original)) == str(key)
                        for (original,) in db.session.query(NucleusData.key_value).filter_by(proyecto_id=pid))
        if not permitido:
            abort(404)


def _escrituras(sesion, *_):
    ctx = contexto()
    if ctx is None:
        return
    for fila in set(sesion.new) | set(sesion.dirty) | set(sesion.deleted):
        if not isinstance(fila, NucleusData):
            continue
        if fila.proyecto_id == request.environ.get('nucleus.importacion_rendicion', {}).get('Rendicion'):
            continue
        if fila.proyecto_id in ctx['compartidos']:
            datos = json.loads(fila.data_json or '{}')
            declaradas = {familia(datos.get(k)) for k in CAMPOS} - {''}
            if declaradas and not declaradas <= ctx['familias']:
                abort(403, 'El registro pertenece a un proyecto no asignado a tu cuenta.')
            if not declaradas:
                if fila in sesion.new or fila in sesion.dirty:
                    # Verificar el mismo criterio SQL sobre los valores nuevos,
                    # sin insertar una fila invisible ni consultar solo el menú.
                    from sqlalchemy import literal
                    candidato = select(literal(fila.proyecto_id).label('proyecto_id'),
                                       literal(fila.key_value).label('key_value'),
                                       literal(fila.data_json).label('data_json')).subquery('nuevo_alcance')
                    with sesion.no_autoflush:
                        admitido = sesion.execute(select(1).select_from(candidato).where(criterio(candidato))).first()
                    if not admitido:
                        abort(403, 'Selecciona un proyecto asignado antes de guardar el registro.')
                    continue
                # También se valida por ID: no basta con conservar una instancia cargada.
                permitido = sesion.execute(select(NucleusData.id).where(NucleusData.id == fila.id)).scalar()
                if permitido is None:
                    abort(403, 'El registro pertenece a un proyecto no asignado a tu cuenta.')
        elif familia(ctx['proyectos'].get(fila.proyecto_id, '')) and fila.proyecto_id not in ctx['operacion']:
            abort(403, 'No tienes asignado este proyecto.')


def instalar():
    if not event.contains(Session, 'do_orm_execute', _consultas):
        event.listen(Session, 'do_orm_execute', _consultas)
        event.listen(Session, 'before_flush', _escrituras)
