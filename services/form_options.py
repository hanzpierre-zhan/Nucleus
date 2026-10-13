"""Editable data choices, shared by tables and forms without rewriting records."""
import re
import unicodedata


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
              for c in columns if c.get('tipo') == 'lista' and normalized(c.get('nombre','')) not in PROTECTED}
    if project_name in ('FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO'):
        for name, values in FLM_CHOICES.items():
            result.setdefault(normalized(name), {'nombre':name,'tipo':'lista','opciones':values,'configurada':False})
    if project_name == 'Cotizaciones':
        result.setdefault(normalized('SUPERVISOR'), {'nombre':'SUPERVISOR','tipo':'lista','opciones':[],'configurada':False})
    return list(result.values())
