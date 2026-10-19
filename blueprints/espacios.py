"""Piloto con rutas propias; los usuarios inscritos no acceden por rutas antiguas."""
import csv
import hashlib
import io
import json
import secrets
from contextlib import contextmanager

from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template,
                   request, session, Response)
from sqlalchemy.exc import IntegrityError
from db import db
from models import (Usuario, Proyecto, NucleusData, PerfilEspacio, AccesoEspacio,
                    ClasificacionEspacio, CuentaEspacio, ProyectoNegocio)
from services.utilidades import login_required
from services import espacios as servicio
from services.usuarios import usuarios_activos

bp = Blueprint('espacios', __name__)


@bp.app_context_processor
def navegacion_proyectos():
    if not current_app.config.get('ESPACIOS_HABILITADOS') or not session.get('user_id'):
        return {}
    if not servicio.es_admin() and not db.session.get(CuentaEspacio, session['user_id']):
        return {}
    permisos = servicio.permisos()
    modulo = request.args.get('modulo', 'operacion')
    visibles = [m for m in servicio.MODULOS if any('consultar' in v.get(m, []) for v in permisos.values())]
    if modulo not in visibles:
        modulo = visibles[0] if visibles else None
    permitidos = servicio.ids_permitidos(modulo) if modulo else set()
    seleccion = request.args.get('proyecto', 'todos')
    if seleccion != 'todos' and seleccion not in {str(p) for p in permitidos}:
        seleccion = 'todos'
    if len(permitidos) == 1:
        seleccion = str(next(iter(permitidos)))
    iconos = {'operacion':'fa-briefcase','personal':'fa-users','materiales':'fa-boxes-stacked',
              'sites':'fa-location-dot','mapa_sites':'fa-map-location-dot','generadores':'fa-bolt',
              'combustible':'fa-gas-pump','cotizaciones':'fa-file-invoice-dollar',
              'rendicion':'fa-wallet','liquidaciones':'fa-file-invoice'}
    return {'navegacion_negocio': {
        'proyectos':[{'id':p.id,'nombre':p.nombre} for p in servicio.proyectos() if p.id in permitidos],
        'seleccion':seleccion,'modulo':modulo,
        'modulos':[{'id':m,'nombre':servicio.MODULOS[m][0],'icono':iconos[m]} for m in visibles],
        'admin':servicio.es_admin()}}


@bp.before_app_request
def aislar_cuentas():
    if not current_app.config.get('ESPACIOS_HABILITADOS'):
        return None
    if not session.get('user_id') or servicio.es_admin():
        return None
    if not db.session.get(CuentaEspacio, session['user_id']):
        return None
    if request.blueprint in ('espacios', 'auth', 'asistencia') or request.endpoint == 'static':
        return None
    if request.path in ('/', '/analytics'):
        return redirect('/espacios')
    if request.path in ('/privacidad', '/terminos', '/cookies'):
        return None
    return jsonify(error='Usa tu espacio de proyecto. El acceso anterior está deshabilitado para esta cuenta.'), 403


@bp.before_request
def comprobar_piloto():
    if not current_app.config.get('ESPACIOS_HABILITADOS'):
        abort(404)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        token = session.get('espacios_csrf', '')
        recibido = request.headers.get('X-Espacios-CSRF', '')
        if not token or not secrets.compare_digest(token, recibido):
            abort(403, 'Recarga la página antes de guardar.')


def _admin():
    if not servicio.es_admin():
        abort(403)


def _modulo(modulo):
    if modulo not in servicio.MODULOS:
        abort(404)


def _payload():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        abort(400, 'Se requiere un objeto de datos válido.')
    return datos


def _seleccion(modulo, accion='consultar'):
    valor = request.args.get('proyecto', 'todos')
    permitidos = servicio.ids_permitidos(modulo, accion)
    if not permitidos:
        abort(403)
    if valor == 'todos':
        return None
    try:
        pid = int(valor)
    except (TypeError, ValueError):
        abort(400, 'Proyecto inválido.')
    if pid not in permitidos:
        abort(403)
    return pid


@bp.route('/espacios')
@login_required
def index():
    if request.args.get('administrar') == '1':
        return redirect('/usuarios')
    session.setdefault('espacios_csrf', secrets.token_urlsafe(32))
    # Recuperar los módulos originales para las cuentas globales. El piloto
    # aislado conserva sus límites hasta adaptar cada flujo nativo con pruebas.
    if servicio.es_admin():
        modulo = request.args.get('modulo', 'operacion')
        if modulo == 'liquidaciones':
            return redirect('/liquidaciones/')
        if modulo == 'mapa_sites':
            return redirect('/mapa-site')
        fuente = servicio.MODULOS.get(modulo, servicio.MODULOS['operacion'])[1]
        if modulo == 'operacion':
            seleccion = request.args.get('proyecto')
            candidatos = servicio.proyectos()
            elegido = next((p for p in candidatos if str(p.id) == seleccion), None)
            if elegido is None:
                elegido = next((p for p in candidatos if p.id == session.get('current_proyecto_id')), None)
            if elegido is None:
                elegido = next((p for p in candidatos if p.nombre == 'FLM - ENTEL'), None)
        else:
            elegido = Proyecto.query.filter_by(nombre=fuente).first()
        return redirect('/switch_project/%s?next=/' % elegido.id) if elegido else redirect('/')
    return render_template('espacios.html', es_admin=False)


def _selecciones_usuario(usuario):
    accesos = AccesoEspacio.query.filter_by(usuario_id=usuario.id).all()
    if db.session.get(CuentaEspacio, usuario.id):
        modulos = set()
        for a in accesos:
            perfil = db.session.get(PerfilEspacio, a.perfil_id)
            if perfil:
                modulos.update(m for m, acciones in json.loads(perfil.permisos_json).items() if 'consultar' in acciones)
        return {'proyectos':[a.proyecto_id for a in accesos], 'modulos':sorted(modulos)}
    from models import AccesoProyecto
    ids = {a.proyecto_id for a in AccesoProyecto.query.filter_by(usuario_id=usuario.id)}
    negocios = {p.id for p in servicio.proyectos()}
    fuentes = {p.nombre:p.id for p in Proyecto.query.all()}
    modulos = [m for m, (_, fuente) in servicio.MODULOS.items() if fuente and fuentes.get(fuente) in ids]
    if ids & negocios:
        modulos.insert(0, 'operacion')
    return {'proyectos':sorted(ids & negocios), 'modulos':modulos}


@bp.app_context_processor
def usuarios_selecciones():
    if request.path != '/usuarios' or not current_app.config.get('ESPACIOS_HABILITADOS') or not servicio.es_admin():
        return {}
    session.setdefault('espacios_csrf', secrets.token_urlsafe(32))
    return {'usuarios_ambitos':{u.id:_selecciones_usuario(u) for u in usuarios_activos()},
            'negocios_usuario':servicio.proyectos(),
            'modulos_usuario':[{'id':m,'nombre':etiqueta} for m,(etiqueta,_) in servicio.MODULOS.items()]}


@bp.route('/api/espacios/usuarios', methods=['POST','PUT'])
@login_required
def guardar_usuario_integrado():
    _admin()
    datos = _payload()
    try:
        nombre = str(datos.get('nombre') or '').strip()
        username = str(datos.get('username') or '').strip()
        rol = str(datos.get('rol') or '').strip()
        if not username or len(username)>80 or rol not in ('zeno','suport','supervisor','gestor','contrata'):
            raise ValueError('Revisa el usuario y el rol.')
        pids, modulos = datos.get('proyectos'), datos.get('modulos')
        if not isinstance(pids,list) or not isinstance(modulos,list):
            raise ValueError('Selecciona proyectos y módulos.')
        pids = {int(p) for p in pids}
        if not pids.issubset({p.id for p in servicio.proyectos()}) or any(m not in servicio.MODULOS for m in modulos):
            raise ValueError('Proyecto o módulo inválido.')
        actual = db.session.get(Usuario,session['user_id'])
        usuario = db.session.get(Usuario,int(datos['id'])) if request.method=='PUT' else None
        if request.method=='PUT' and not usuario:
            abort(404)
        if actual.rol == 'suport' and (rol == 'zeno' or (usuario and usuario.rol=='zeno')):
            abort(403)
        if rol != 'zeno' and (not pids or not modulos):
            raise ValueError('Selecciona al menos un proyecto y un módulo.')
        clave = datos.get('password') or ''
        if not usuario and not clave:
            raise ValueError('La nueva cuenta requiere una contraseña.')
        if not usuario:
            usuario = Usuario()
            db.session.add(usuario)
        usuario.nombre,usuario.username,usuario.rol = nombre,username,rol
        if clave:
            from werkzeug.security import generate_password_hash
            usuario.password_hash = generate_password_hash(clave)
        db.session.flush()
        AccesoEspacio.query.filter_by(usuario_id=usuario.id).delete()
        if rol != 'zeno':
            permisos = {}
            for m in set(modulos):
                acciones = ['consultar','exportar'] if rol!='contrata' else ['consultar']
                if rol in ('gestor','supervisor') and m not in ('liquidaciones','mapa_sites'):
                    acciones.append('editar')
                if rol=='supervisor' and m=='rendicion':
                    acciones += ['validar','rechazar','observar','sustentar']
                permisos[m] = acciones
            perfil = PerfilEspacio.query.filter_by(nombre='Cuenta · '+str(usuario.id)).first()
            if not perfil:
                perfil = PerfilEspacio(nombre='Cuenta · '+str(usuario.id))
                db.session.add(perfil)
            perfil.permisos_json = json.dumps(servicio.validar_permisos(permisos))
            db.session.flush()
            for pid in pids:
                db.session.add(AccesoEspacio(usuario_id=usuario.id,proyecto_id=pid,perfil_id=perfil.id))
            if not db.session.get(CuentaEspacio,usuario.id):
                db.session.add(CuentaEspacio(usuario_id=usuario.id))
        servicio.auditar('guardar_usuario',{'usuario':usuario.id,'proyectos':sorted(pids),'modulos':sorted(set(modulos)),'rol':rol})
        db.session.commit()
        return jsonify(success=True,id=usuario.id)
    except (ValueError,TypeError) as error:
        db.session.rollback()
        return jsonify(error=str(error)),400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='El nombre de usuario ya existe. No se guardó ningún cambio.'),409


@bp.route('/api/espacios/contexto')
@login_required
def contexto():
    permitidos = servicio.permisos()
    nombres = servicio.etiquetas_proyectos()
    return jsonify(proyectos=[{'id': p.id, 'nombre': p.nombre,
                                'permisos': permitidos[p.id]} for p in servicio.proyectos()
                               if p.id in permitidos and permitidos[p.id]],
                   modulos=[{'id': m, 'nombre': etiqueta} for m, (etiqueta, _) in servicio.MODULOS.items()],
                   admin=servicio.es_admin())


@bp.route('/api/espacios/<modulo>/mapa')
@login_required
def mapa(modulo):
    if modulo != 'mapa_sites':
        abort(404)
    filas = servicio.registros(modulo, _seleccion(modulo))
    termino = request.args.get('buscar', '').strip().casefold()
    puntos, sin_coordenadas = [], 0
    for f in filas:
        d = f['datos']
        if termino and termino not in json.dumps(f, ensure_ascii=False).casefold():
            continue
        try:
            lat = float(str(d.get('Latitud (°)') or d.get('Latitud') or d.get('LATITUD') or '').replace(',', '.'))
            lng = float(str(d.get('Longitud (°)') or d.get('Longitud') or d.get('LONGITUD') or '').replace(',', '.'))
            if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
                raise ValueError()
        except (ValueError, TypeError):
            sin_coordenadas += 1
            continue
        puntos.append({'id':f['id'],'nombre':d.get('NOMBRE DE SITE') or d.get('Nombre de Site') or f['clave'],
                       'proyecto':f['proyecto'],'lat':lat,'lng':lng})
    return jsonify(puntos=puntos, sin_coordenadas=sin_coordenadas)


@bp.route('/api/espacios/<modulo>/registros')
@login_required
def listar(modulo):
    _modulo(modulo)
    seleccion = _seleccion(modulo)
    filas = servicio.registros(modulo, seleccion)
    termino = request.args.get('buscar', '').strip().casefold()
    if termino:
        filas = [f for f in filas if termino in json.dumps(f, ensure_ascii=False).casefold()]
    try:
        pagina = max(1, int(request.args.get('pagina', 1)))
        limite = min(100, max(1, int(request.args.get('limite', 30))))
    except ValueError:
        abort(400)
    total = len(filas)
    pagina = min(pagina, max(1, (total + limite - 1) // limite))
    return jsonify(registros=filas[(pagina-1)*limite:pagina*limite], total=total,
                   pagina=pagina, limite=limite)


@bp.route('/api/espacios/<modulo>/exportar')
@login_required
def exportar(modulo):
    _modulo(modulo)
    seleccion = _seleccion(modulo, 'exportar')
    filas = servicio.registros(modulo, seleccion, 'exportar')
    campos = sorted({k for f in filas for k in f['datos']})
    salida = io.StringIO()
    escritor = csv.writer(salida)
    def seguro(valor):
        texto = json.dumps(valor, ensure_ascii=False) if isinstance(valor, (list, dict)) else str(valor or '')
        return "'" + texto if texto.lstrip().startswith(('=', '+', '-', '@')) else texto
    escritor.writerow(['Proyecto', 'Clave'] + campos)
    for fila in filas:
        escritor.writerow([seguro(fila['proyecto']), seguro(fila['clave'])] +
                          [seguro(fila['datos'].get(c)) for c in campos])
    servicio.auditar('exportar', {'modulo': modulo, 'proyecto': seleccion, 'filas': len(filas)})
    db.session.commit()
    return Response('\ufeff' + salida.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="%s.csv"' % modulo})


def _registro(modulo, rid, accion):
    # Comprueba pertenencia además de permiso de módulo, incluso con ID adivinado.
    if not any(f['id'] == rid for f in servicio.registros(modulo, accion=accion)):
        abort(404)
    fila = NucleusData.query.filter_by(id=rid).with_for_update().first_or_404()
    return fila


@contextmanager
def _contexto_anterior(fila):
    claves = ('current_proyecto_id', 'current_proyecto_nombre', 'flm_resource_context')
    anterior = {c: session.get(c) for c in claves}
    fuente = db.session.get(Proyecto, fila.proyecto_id)
    session['current_proyecto_id'] = fuente.id
    session['current_proyecto_nombre'] = fuente.nombre
    session.pop('flm_resource_context', None)
    try:
        yield
    finally:
        for clave, valor in anterior.items():
            if valor is None:
                session.pop(clave, None)
            else:
                session[clave] = valor


@bp.route('/api/espacios/<modulo>/registros/<int:rid>', methods=['PATCH'])
@login_required
def editar(modulo, rid):
    _modulo(modulo)
    if modulo == 'liquidaciones':
        abort(403)
    fila = _registro(modulo, rid, 'editar')
    datos = _payload()
    campo = datos.get('field')
    if (not isinstance(campo, str) or campo.startswith('_')
            or servicio.normalizar(campo) in servicio.PROTEGIDOS | {
                'numerowo', 'numerodewo', 'wonumber', 'tipodeproyecto'}):
        abort(400, 'Ese campo se administra desde su proceso; no se puede cambiar aquí.')
    actuales = servicio._datos(fila)
    if campo not in actuales or datos.get('key') != fila.key_value:
        abort(400, 'Campo o registro inválido.')
    revision = hashlib.sha256(fila.data_json.encode()).hexdigest()
    # La versión enviada protege contra guardar un detalle que ya cambió.
    if datos.get('revision') != revision:
        abort(409, 'El registro cambió. Vuelve a abrirlo antes de guardar.')
    from blueprints.rows import api_rows_update
    with _contexto_anterior(fila):
        return api_rows_update()


@bp.route('/api/espacios/<modulo>/registros/<int:rid>')
@login_required
def detalle(modulo, rid):
    _modulo(modulo)
    fila = _registro(modulo, rid, 'consultar')
    registro = next(f for f in servicio.registros(modulo) if f['id'] == rid)
    registro['revision'] = hashlib.sha256(fila.data_json.encode()).hexdigest()
    return jsonify(registro)


@bp.route('/api/espacios/rendicion/registros/<int:rid>/accion', methods=['POST'])
@login_required
def accion_rendicion(rid):
    datos = _payload()
    accion = datos.get('accion')
    if accion not in servicio.ACCIONES - {'consultar', 'exportar', 'editar'}:
        abort(400)
    fila = _registro('rendicion', rid, accion)
    if datos.get('key') != fila.key_value:
        abort(400)
    from blueprints.rendicion import api_rendicion_accion
    with _contexto_anterior(fila):
        return api_rendicion_accion()


@bp.route('/api/espacios/administracion')
@login_required
def administracion():
    _admin()
    return jsonify(usuarios=[{'id': u.id, 'nombre': u.nombre or u.username, 'rol':u.rol,
                             'administrador_global':u.rol == 'zeno'}
                            for u in usuarios_activos().order_by(Usuario.username)],
                   perfiles=[{'id': p.id, 'nombre': p.nombre, 'permisos': json.loads(p.permisos_json)}
                             for p in PerfilEspacio.query.order_by(PerfilEspacio.nombre)],
                   accesos=[{'id': a.id, 'usuario_id': a.usuario_id, 'proyecto_id': a.proyecto_id,
                             'perfil_id': a.perfil_id} for a in AccesoEspacio.query.all()],
                   acciones=sorted(servicio.ACCIONES))


@bp.route('/api/espacios/perfiles/sugeridos', methods=['POST'])
@login_required
def sugerir_perfiles():
    _admin()
    creados = []
    for nombre, permisos in servicio.perfiles_sugeridos().items():
        if not PerfilEspacio.query.filter_by(nombre=nombre).first():
            db.session.add(PerfilEspacio(nombre=nombre, permisos_json=json.dumps(
                servicio.validar_permisos(permisos))))
            creados.append(nombre)
    servicio.auditar('crear_perfiles_sugeridos', {'creados':creados})
    db.session.commit()
    return jsonify(success=True, creados=creados)


@bp.route('/api/espacios/perfiles', methods=['POST'])
@login_required
def perfil():
    _admin()
    datos = _payload()
    try:
        nombre = str(datos.get('nombre') or '').strip()
        if not nombre or len(nombre) > 80:
            raise ValueError('El nombre debe tener entre 1 y 80 caracteres.')
        permisos = servicio.validar_permisos(datos.get('permisos'))
        perfil = db.session.get(PerfilEspacio, int(datos['id'])) if datos.get('id') else PerfilEspacio()
        if perfil is None:
            abort(404)
        perfil.nombre = nombre
        perfil.permisos_json = json.dumps(permisos)
        db.session.add(perfil)
        db.session.flush()
        servicio.auditar('guardar_perfil', {'id': perfil.id, 'nombre': nombre, 'permisos': permisos})
        db.session.commit()
        return jsonify(success=True, id=perfil.id)
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='Ya existe un perfil con ese nombre.'), 409


@bp.route('/api/espacios/asignaciones', methods=['POST'])
@login_required
def asignar():
    _admin()
    datos = _payload()
    try:
        uid, perfil_id = (int(datos[c]) for c in ('usuario_id', 'perfil_id'))
        pids = datos.get('proyecto_ids', [datos.get('proyecto_id')])
        if not isinstance(pids,list) or not pids:
            raise ValueError()
        pids = sorted({int(pid) for pid in pids})
    except (KeyError, TypeError, ValueError):
        abort(400)
    usuario = db.session.get(Usuario, uid)
    if (not usuario or not set(pids).issubset({p.id for p in servicio.proyectos()})
            or not db.session.get(PerfilEspacio, perfil_id)):
        abort(400)
    if usuario.rol == 'zeno':
        abort(400, 'Zeno mantiene acceso global.')
    for pid in pids:
        acceso = AccesoEspacio.query.filter_by(usuario_id=uid, proyecto_id=pid).first()
        if acceso is None:
            acceso = AccesoEspacio(usuario_id=uid, proyecto_id=pid)
            db.session.add(acceso)
        acceso.perfil_id = perfil_id
    if not db.session.get(CuentaEspacio, uid):
        db.session.add(CuentaEspacio(usuario_id=uid))
    servicio.auditar('asignar', {'usuario': uid, 'proyectos': pids, 'perfil': perfil_id})
    db.session.commit()
    return jsonify(success=True)


@bp.route('/api/espacios/proyectos', methods=['POST'])
@login_required
def nuevo_proyecto():
    _admin()
    datos = _payload()
    nombre = str(datos.get('nombre') or '').strip()
    if not nombre or len(nombre) > 60:
        abort(400, 'Indica un nombre de hasta 60 caracteres.')
    nombres_actuales = [p.nombre for p in servicio.proyectos()] + list(servicio.etiquetas_proyectos().values())
    if servicio.nombre_negocio(nombre) or any(servicio.normalizar(nombre) == servicio.normalizar(n) for n in nombres_actuales):
        abort(409, 'Ese proyecto ya existe o coincide con un nombre reservado.')
    try:
        proyecto = Proyecto(nombre='FLM - ' + nombre.upper(), descripcion='Espacio de negocio: ' + nombre)
        db.session.add(proyecto); db.session.flush()
        db.session.add(ProyectoNegocio(proyecto_id=proyecto.id, nombre=nombre))
        servicio.auditar('crear_proyecto', {'id': proyecto.id, 'nombre': nombre})
        db.session.commit()
        return jsonify(success=True, id=proyecto.id)
    except IntegrityError:
        db.session.rollback()
        abort(409, 'Ya existe ese proyecto.')


@bp.route('/api/espacios/asignaciones/<int:aid>', methods=['DELETE'])
@login_required
def revocar(aid):
    _admin()
    acceso = db.session.get(AccesoEspacio, aid)
    if acceso is None:
        abort(404)
    servicio.auditar('revocar', {'usuario': acceso.usuario_id, 'proyecto': acceso.proyecto_id})
    db.session.delete(acceso)
    db.session.commit()
    return jsonify(success=True)


@bp.route('/api/espacios/pendientes')
@login_required
def pendientes():
    _admin()
    filas = [{'id': f.id, 'clave': f.key_value, 'modulo': fuente}
             for f, _, fuente, negocio in servicio.atribuciones()
             if negocio is None and fuente in {v for _, v in servicio.MODULOS.values()}]
    return jsonify(total=len(filas), registros=filas[:100])


@bp.route('/api/espacios/clasificaciones', methods=['POST'])
@login_required
def clasificar():
    _admin()
    datos = _payload()
    try:
        rid, pid = int(datos['registro_id']), int(datos['proyecto_id'])
    except (KeyError, ValueError, TypeError):
        abort(400)
    fila = db.session.get(NucleusData, rid)
    if not fila or pid not in {p.id for p in servicio.proyectos()}:
        abort(400)
    if not str(datos.get('motivo') or '').strip():
        abort(400, 'Indica el motivo de la clasificación.')
    fuente = db.session.get(Proyecto, fila.proyecto_id)
    if fuente.id in {p.id for p in servicio.proyectos()}:
        abort(400, 'El registro operativo ya pertenece a su proyecto.')
    clasificacion = db.session.get(ClasificacionEspacio, rid)
    if clasificacion is None:
        clasificacion = ClasificacionEspacio(registro_id=rid)
        db.session.add(clasificacion)
    previo = clasificacion.proyecto_id
    clasificacion.proyecto_id = pid
    servicio.auditar('clasificar', {'registro': rid, 'anterior': previo, 'proyecto': pid,
                                   'motivo': str(datos.get('motivo') or '')[:500]})
    db.session.commit()
    return jsonify(success=True)
