"""Dimensiones de consulta: lectura de campos reales, sin inferir cobros."""
from services.normalizacion import normalizar, primer_texto
from services.dashboard_integratel import fecha


def valor(row, *campos):
    indice = {normalizar(k): v for k, v in row.items()}
    for campo in campos:
        v = indice.get(normalizar(campo))
        if v is not None and str(v).strip():
            return v
    return ''


def proyecto(nombre):
    familias = {'entel': 'ENTEL', 'flm': 'ENTEL', 'flmentel': 'ENTEL',
                'claro': 'CLARO', 'flmclaro': 'CLARO', 'integratel': 'INTEGRATEL',
                'flmintegratel': 'INTEGRATEL', 'pext': 'PEXT', 'flmpext': 'PEXT',
                'entelpext': 'PEXT', 'flmentelpext': 'PEXT'}
    familia = familias.get(normalizar(nombre))
    return 'FLM - ' + familia if familia else primer_texto(nombre) or 'Sin proyecto'


def gasto(nombre, vacio):
    return {'gastocobra': 'Gasto Cobra', 'refacturable': 'Refacturable',
            'cajachica': 'Caja Chica', 'proveedor': 'Proveedor'}.get(normalizar(nombre), primer_texto(nombre) or vacio)


def dia(valor):
    f = fecha(valor)
    return f.isoformat()[:10] if f else ''


def validacion_sustento(row):
    return (str(row.get('_SUSTENTO_APROBADO') or '').strip() == '1'
            or str(row.get('_SUSTENTO_VALIDADO') or '').strip() == '1'
            or bool(fecha(row.get('_SUSTENTO_VALIDADO'))))


def comunes(row):
    return {
        'departamento': primer_texto(valor(row, 'DEPARTAMENTO')) or 'Sin departamento',
        'registrador': primer_texto(valor(row, 'REGISTRADO POR', 'CREADO POR')) or 'Sin registrador',
        'nombre': primer_texto(valor(row, 'NOMBRE', 'NOMBRE COMPLETO', 'Técnico beneficiario', 'TECNICO')) or 'Sin nombre',
    }


def espera(row, hoy, campos, estado=None, cerrado=False):
    eventos = row.get('_HISTORIAL_FLUJO')
    if isinstance(eventos, list) and eventos and isinstance(eventos[-1], dict):
        ultimo = eventos[-1]
        if estado is not None and ultimo.get('hasta') == estado:
            campos = [('_HISTORIAL_FLUJO', ultimo.get('fecha'))]
        else:
            campos = [(k, row.get(k)) for k in campos]
    else:
        campos = [(k, row.get(k)) for k in campos]
    for campo, v in campos:
        f = fecha(v)
        if f:
            return {'dias_etapa': (hoy - f).days if f <= hoy and not cerrado else None,
                    'fecha_etapa': f.isoformat(), 'fuente_fecha_etapa': campo + (' · fecha futura' if f > hoy else '')}
    return {'dias_etapa': None, 'fecha_etapa': '', 'fuente_fecha_etapa': 'Sin fecha de etapa'}
