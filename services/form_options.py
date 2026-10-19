"""Editable data choices, shared by tables and forms without rewriting records."""
import re
import unicodedata


def instalar_pext():
    """Añadir PEXT una sola vez a las listas existentes sin cambiar cotizaciones."""
    import json
    from db import db
    from models import Proyecto, AppConfig
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not proyecto or AppConfig.query.filter_by(proyecto_id=proyecto.id, clave='cot_pext_opcion_v1').first():
        return
    config = AppConfig.query.filter_by(proyecto_id=proyecto.id, clave='manual_columns').first()
    if config:
        columnas = json.loads(config.valor)
        for columna in columnas:
            if columna.get('nombre') == 'CLIENTE' and columna.get('tipo') == 'lista':
                opciones = columna.setdefault('opciones', [])
                if 'PEXT' not in opciones:
                    opciones.append('PEXT')
        config.valor = json.dumps(columnas, ensure_ascii=False)
    db.session.add(AppConfig(proyecto_id=proyecto.id, clave='cot_pext_opcion_v1', valor='1'))
    db.session.commit()


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower())


FLM_CHOICES = {
    'SERVICIO': [], 'SISTEMAS': [], 'SOLUCIÓN': [], 'TECNICO ASIGNADO': [],
    'SE INSTALÓ MUFAS': ['GEP','GEE','NA'],
    'REQUIERE CORRECTIVO FINAL': ['Sí','No'], 'REQUIERE BIÁTICOS': ['Sí','No'],
    '¿REQUIERE MATERIAL?': ['Sí','No'], '¿REQUIERE ACCESO AL SITE?': ['Sí','No'],
    '¿FUE TORRERA?': ['Sí','No'], '¿FUE SITE PROPIO?': ['Sí','No'],
    '¿CUADRILLA DE 3 O 2?': ['2','3'],
    'TEAM LEADER ASIGNADO EN APLICATIVO': [],
    '¿QUIÉN FUE EL SUPERVISOR A CARGO EN ESE TURNO?': [],
    'STATUS DE ATENCION': ['PROCESO','SUSPENDIDO','TERMINADO'],
    '¿QUEDO PENDIENTE ALGUN CORRECTIVO ADICIONAL?': ['Sí','No'],
}

# These choices drive routing, authorization or workflow transitions.
PROTECTED = {normalized(x) for x in ('CLIENTE','PROYECTO','ROL','ESTADO COTIZACION',
             'ESTADO','ESTADO DE LIQUIDACION','MOVIMIENTO','TIPO GASTO COTIZACION',
             'QR ASIGNADO','WO NUMBER','NUMERO WO','NÚMERO DE WO','N° COTIZACION')}


def choices(columns, project_name):
    result = {normalized(c['nombre']): {**c, 'configurada':True}
              for c in columns if c.get('tipo') == 'lista' and (normalized(c.get('nombre','')) not in PROTECTED
                  or (project_name == 'Cotizaciones' and c.get('nombre') == 'CLIENTE'))}
    if project_name in ('FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO','FLM - PEXT'):
        for name, values in FLM_CHOICES.items():
            result.setdefault(normalized(name), {'nombre':name,'tipo':'lista','opciones':values,'configurada':False})
    if project_name == 'Cotizaciones':
        result.setdefault(normalized('CLIENTE'), {'nombre':'CLIENTE','tipo':'lista','opciones':['ENTEL','CLARO','INTEGRATEL','PEXT'],'configurada':False})
        result.setdefault(normalized('NOMBRE SITE'), {'nombre':'NOMBRE SITE','tipo':'lista','opciones':[],'configurada':False})
        result.setdefault(normalized('NOMBRE CLIENTE'), {'nombre':'NOMBRE CLIENTE','tipo':'lista','opciones':[],'configurada':False})
        result.setdefault(normalized('TIPO DE GASTO'), {'nombre':'TIPO DE GASTO','tipo':'lista','opciones':['Gasto Cobra','Refacturable'],'configurada':False})
        result.setdefault(normalized('SUPERVISOR'), {'nombre':'SUPERVISOR','tipo':'lista','opciones':[],'configurada':False})
    from services.alcance_proyectos import limitar_opciones
    return limitar_opciones(list(result.values()))
