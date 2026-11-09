"""Vistas nuevas (en prueba) con el diseño de Caja Chica: Dataper, Material, Sites, Combustible y Usuarios.

Leen los mismos datos de cada módulo; para editar reutilizan /api/rows/* (con todas sus validaciones),
por eso al abrir la vista se fija el módulo en la sesión, igual que /switch_project.
"""
import io
import json
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, jsonify, render_template, request, send_file, session

from models import AccesoProyecto, AppConfig, NucleusData, Proyecto
from services import get_menu_proyectos, login_required
from services.recursos_flm import familia

bp = Blueprint('vistas_nuevas', __name__)
ROLES_TODO = ('zeno', 'suport', 'admin')
FAMILIAS = (('ENTEL', 'Entel', '#2563eb'), ('CLARO', 'Claro', '#dc2626'), ('INTEGRATEL', 'Integratel', '#16a34a'),
            ('PEXT', 'PEXT', '#f08a1c'))

# slug: (proyecto, título, icono, campo de pestaña, pestañas, campo clave visible, campo a sumar, unidad)
MODULOS = {
    'dataper': ('Dataper', 'Dataper', 'fa-users', 'PROYECTO', 'familias', 'DOCUMENTO', None, ''),
    'material': ('Material', 'Material', 'fa-boxes-stacked', 'PROYECTO', 'familias', 'COD_MATERIAL', None, ''),
    'sites': ('SITE', 'Sites', 'fa-location-dot', 'Proyecto', 'familias', 'Código del sitio | Site ID', None, ''),
    'combustible': ('Combustible', 'Combustible', 'fa-gas-pump', 'MOVIMIENTO',
                    (('INGRESO', 'Ingreso', '#16a34a'), ('GASTO', 'Gasto', '#dc2626')), 'ID DE REPORTE', 'GALONES', 'gal'),
}


def _rol():
    return str(session.get('rol') or '').strip().lower()


def _modulo(slug):
    if slug not in MODULOS:
        abort(404)
    nombre = MODULOS[slug][0]
    proyecto = next((p for p in get_menu_proyectos(session.get('user_id'), session.get('rol')) if p.nombre == nombre), None)
    if proyecto is None:
        abort(403)
    return proyecto


def _pestanas(slug):
    definicion = MODULOS[slug][4]
    return FAMILIAS if definicion == 'familias' else definicion


def _clave_pestana(slug, datos):
    campo = MODULOS[slug][3]
    valor = str(datos.get(campo) or '').strip()
    return (familia(valor) or 'OTROS') if MODULOS[slug][4] == 'familias' else (valor.upper() or 'OTROS')


def _columnas(proyecto, filas):
    """Orden y visibilidad del layout guardado del módulo; si no hay, los campos más usados."""
    cfg = AppConfig.query.filter_by(proyecto_id=proyecto.id, clave='column_layout').first()
    try:
        layout = json.loads(cfg.valor) if cfg and cfg.valor else []
    except ValueError:
        layout = []
    visibles = [c['field'] for c in layout if isinstance(c, dict) and c.get('field') and c.get('visible') is not False
                and not str(c['field']).startswith('_')]
    conteo = {}
    for f in filas[:500]:
        for k in f['datos']:
            if not str(k).startswith('_') and k not in ('EDITADO POR', 'undefined'):
                conteo[k] = conteo.get(k, 0) + 1
    if visibles:
        return [c for c in visibles if c in conteo] or list(conteo)
    return sorted(conteo, key=lambda k: -conteo[k])


@bp.get('/vista/<slug>/')
@login_required
def pagina(slug):
    proyecto = _modulo(slug)
    # Las ediciones usan /api/rows/*, que trabajan sobre el módulo de la sesión (igual que /switch_project).
    session.pop('flm_resource_context', None)
    session['current_proyecto_id'], session['current_proyecto_nombre'] = int(proyecto.id), proyecto.nombre
    _, titulo, icono, _, _, clave, suma, unidad = MODULOS[slug]
    rol = _rol()
    return render_template('vista_nueva.html', slug=slug, titulo=titulo, icono=icono, proyecto_id=proyecto.id,
                           pestanas=_pestanas(slug), campo_clave=clave, unidad=unidad, suma=suma or '',
                           puede_editar=rol not in ('demo', 'contrata') and (slug != 'sites' or rol in ('zeno', 'suport', 'supervisor')),
                           puede_clave=slug == 'dataper' and rol not in ('demo', 'contrata'), proyectos=None,
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')))


@bp.get('/api/vista/<slug>/lista')
@login_required
def lista(slug):
    proyecto = _modulo(slug)
    permitidas = None
    if _rol() not in ROLES_TODO and MODULOS[slug][4] == 'familias':
        from services.recursos_flm import familias_permitidas
        permitidas = familias_permitidas()
    filas = []
    for rid, key, crudo in (NucleusData.query.filter_by(proyecto_id=proyecto.id)
                            .with_entities(NucleusData.id, NucleusData.key_value, NucleusData.data_json)
                            .order_by(NucleusData.id.desc())):
        try:
            datos = json.loads(crudo or '{}')
        except ValueError:
            continue
        pestana = _clave_pestana(slug, datos)
        if permitidas is not None and pestana not in permitidas:
            continue
        filas.append({'id': rid, 'key': key, 'pestana': pestana,
                      'datos': {k: v for k, v in datos.items() if not str(k).startswith('_') and not isinstance(v, (dict, list))}})
    return jsonify(columnas=_columnas(proyecto, filas), filas=filas)


def _fijar_modulo(slug):
    """Las ediciones reutilizan /api/rows/*, que trabaja sobre el módulo de la sesión: se fija aquí
    para que dos vistas abiertas a la vez no guarden en el módulo equivocado."""
    proyecto = _modulo(slug)
    session.pop('flm_resource_context', None)
    session['current_proyecto_id'], session['current_proyecto_nombre'] = int(proyecto.id), proyecto.nombre


@bp.post('/api/vista/<slug>/actualizar')
@login_required
def actualizar(slug):
    _fijar_modulo(slug)
    from blueprints.rows import api_rows_update
    return api_rows_update()


@bp.post('/api/vista/<slug>/agregar')
@login_required
def agregar(slug):
    _fijar_modulo(slug)
    from blueprints.rows import api_rows_add
    return api_rows_add()


@bp.post('/api/vista/<slug>/exportar')
@login_required
def exportar(slug):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    datos = request.get_json(silent=True) or {}
    ids, columnas = datos.get('ids'), datos.get('columnas')
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 50000 or any(type(i) is not int for i in ids)
            or not isinstance(columnas, list) or not all(isinstance(c, str) for c in columnas)):
        return jsonify(error='Selecciona registros válidos para exportar.'), 400
    proyecto = _modulo(slug)
    elegidos = set(ids)
    libro = Workbook()
    hoja = libro.active
    hoja.title = MODULOS[slug][1][:30]
    hoja.append(['ID', *columnas])
    for rid, key, crudo in (NucleusData.query.filter(NucleusData.proyecto_id == proyecto.id, NucleusData.id.in_(elegidos))
                            .with_entities(NucleusData.id, NucleusData.key_value, NucleusData.data_json)):
        fila = json.loads(crudo or '{}')
        valores = [key, *(fila.get(c, '') for c in columnas)]
        hoja.append([ILLEGAL_CHARACTERS_RE.sub('', str(v)) if v not in (None, '') else '' for v in valores])
    hoja.freeze_panes = 'A2'
    hoja.auto_filter.ref = hoja.dimensions
    for columna in hoja.columns:
        titulo = columna[0]
        titulo.font = Font(bold=True, color='FFFFFF')
        titulo.fill = PatternFill('solid', fgColor='166534')
        hoja.column_dimensions[get_column_letter(titulo.column)].width = min(40, max(10, *(len(str(c.value or '')) + 2 for c in columna[:300])))
    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    return send_file(archivo, as_attachment=True, download_name=MODULOS[slug][1] + '.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── Usuarios ────────────────────────────────────────────────────────────────

ROLES_USUARIO = (('zeno', 'Zeno', '#7c3aed'), ('suport', 'Suport', '#2563eb'), ('admin', 'Admin', '#0891b2'),
                 ('supervisor', 'Supervisor', '#16a34a'), ('gestor', 'Gestor', '#f08a1c'), ('contrata', 'Contrata', '#a14a08'),
                 ('demo', 'Demo', '#94a3b8'))


def _solo_admin():
    if _rol() not in ('zeno', 'suport'):
        abort(403)


@bp.get('/vista/usuarios/')
@login_required
def usuarios():
    _solo_admin()
    proyectos = Proyecto.query.order_by(Proyecto.id).all()
    return render_template('vista_nueva.html', slug='usuarios', titulo='Usuarios', icono='fa-user', proyecto_id=0,
                           pestanas=ROLES_USUARIO, campo_clave='Usuario', unidad='', suma='', puede_editar=True,
                           puede_clave=False, proyectos=[{'id': p.id, 'nombre': p.nombre} for p in proyectos],
                           proyectos_list=get_menu_proyectos(session.get('user_id'), session.get('rol')))


@bp.get('/api/vista/usuarios/lista')
@login_required
def usuarios_lista():
    _solo_admin()
    from services.usuarios import usuarios_activos
    accesos = {}
    for a in AccesoProyecto.query.all():
        accesos.setdefault(a.usuario_id, []).append(a.proyecto_id)
    from services.caja_chica import depositantes
    marcados = depositantes()
    return jsonify(usuarios=[{'id': u.id, 'nombre': u.nombre or '', 'username': u.username, 'rol': u.rol or '',
                              'proyectos': accesos.get(u.id, []), 'depositante': u.id in marcados}
                             for u in usuarios_activos().all()])


@bp.post('/api/vista/usuarios/depositante')
@login_required
def usuarios_depositante():
    """Marca al usuario como depositante de Caja Chica en el celular."""
    _solo_admin()
    from models import Usuario
    from services.caja_chica import marcar_depositante
    datos = request.get_json(silent=True) or {}
    uid = datos.get('id')
    from db import db
    if type(uid) is not int or not db.session.get(Usuario, uid):
        return jsonify(error='Usuario no válido.'), 400
    marcar_depositante(uid, datos.get('activo') is True)
    return jsonify(success=True)
