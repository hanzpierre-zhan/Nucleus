from flask import Blueprint,jsonify,session,request,redirect,abort
from db import db
from models import Proyecto
from services.utilidades import login_required,get_menu_proyectos
from services.recursos_flm import FLM_NOMBRES
bp=Blueprint('recursos',__name__)

@bp.route('/flm/<int:flm_id>/recursos/<recurso>')
@login_required
def abrir(flm_id,recurso):
    origen=db.session.get(Proyecto,flm_id)
    if not origen or origen.nombre not in FLM_NOMBRES: abort(404)
    permitidos=get_menu_proyectos(session.get('user_id'),session.get('rol'))
    if not any(p.id==flm_id for p in permitidos): abort(403)
    catalogos={'personal':'Dataper','material':'Material','sites':'SITE','mapa':'SITE','generadores':'Generadores'}
    if recurso not in catalogos: abort(404)
    catalogo=Proyecto.query.filter_by(nombre=catalogos[recurso]).first()
    if not catalogo: abort(404)
    if not any(p.id==catalogo.id for p in permitidos): abort(403)
    session['current_proyecto_id']=catalogo.id
    session['current_proyecto_nombre']=catalogo.nombre
    session['flm_resource_context']={'flm_id':flm_id,'catalogo_id':catalogo.id,'recurso':recurso}
    return redirect('/mapa-site' if recurso=='mapa' else '/')

@bp.route('/api/catalogos/autocompletar')
@login_required
def sugerencias():
    # Sugerencias de los campos "site" / "nombre de site" de todos los módulos.
    # Fuente única: el maestro SITE (ver services/sites_maestro). Antes este
    # endpoint no reconocía la columna 'Nombre' del maestro y devolvía siempre
    # una lista vacía.
    from services.sites_maestro import nombres_maestro
    departamentos=['Amazonas','Áncash','Apurímac','Arequipa','Ayacucho','Cajamarca','Callao','Cusco','Huancavelica','Huánuco','Ica','Junín','La Libertad','Lambayeque','Lima','Loreto','Madre de Dios','Moquegua','Pasco','Piura','Puno','San Martín','Tacna','Tumbes','Ucayali']
    return jsonify({'departamentos':departamentos,'sites':nombres_maestro()})


@bp.before_app_request
def contexto_api_explicito():
    if not request.path.startswith('/api/') or not request.headers.get('X-FLM-Origin') or not session.get('user_id'):
        return None
    try:
        origen_id=int(request.headers['X-FLM-Origin'])
        proyecto_id=int(request.headers.get('X-Nucleus-Project',''))
    except ValueError:
        return jsonify({'error':'Contexto de proyecto inválido.'}),400
    permitidos={p.id:p for p in get_menu_proyectos(session.get('user_id'),session.get('rol'))}
    origen=permitidos.get(origen_id)
    destino=permitidos.get(proyecto_id)
    if not origen or origen.nombre not in FLM_NOMBRES or not destino:
        return jsonify({'error':'No tienes acceso al proyecto solicitado.'}),403
    if proyecto_id!=origen_id and destino.nombre not in ('Dataper','Material','SITE','Generadores'):
        return jsonify({'error':'El recurso no corresponde al FLM indicado.'}),403
    session['current_proyecto_id']=proyecto_id
    session['current_proyecto_nombre']=destino.nombre
    if proyecto_id==origen_id:
        session.pop('flm_resource_context',None)
    else:
        slug={'Dataper':'personal','Material':'material','SITE':'sites','Generadores':'generadores'}[destino.nombre]
        session['flm_resource_context']={'flm_id':origen_id,'catalogo_id':proyecto_id,'recurso':slug}
