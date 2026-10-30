"""Cruce de nuevas solicitudes con el catálogo de Personal (Dataper)."""
import json
import re
from services.normalizacion import normalizar
from models import Proyecto, NucleusData


def _homologar(datos):
    from flask import has_app_context, has_request_context, request
    if not has_app_context():
        return datos
    from models import AppConfig
    from services.rendicion_homologacion import aplicar
    cache = request.environ if has_request_context() else {}
    clave = 'nucleus.rendicion_nombres_homologados'
    if clave not in cache:
        proyecto = Proyecto.query.filter_by(nombre='Rendicion').first()
        cfg = AppConfig.query.filter_by(proyecto_id=proyecto.id, clave='rendicion_nombres_homologados').first() if proyecto else None
        cache[clave] = json.loads(cfg.valor) if cfg else {}
    return aplicar(datos, cache[clave])




def documento(valor):
    # Texto: jamás convertir a entero ni eliminar ceros iniciales.
    return re.sub(r'[\s.\-]', '', str(valor or '')).upper()


def campo(datos, aliases):
    permitidos = {normalizar(x) for x in aliases}
    return next((k for k in datos if normalizar(k) in permitidos), None)


def indice_personal():
    proyecto = Proyecto.query.filter_by(nombre='Dataper').first()
    indice = {}
    if not proyecto:
        return indice
    for registro in NucleusData.query.filter_by(proyecto_id=proyecto.id).yield_per(500):
        try:
            datos = json.loads(registro.data_json or '{}')
        except (ValueError, TypeError):
            continue
        if not isinstance(datos, dict):
            continue
        doc_key = campo(datos, ['DOCUMENTO','DNI','NUMERO DE DOCUMENTO','NRO DOCUMENTO'])
        name_key = campo(datos, ['TECNICO','NOMBRE DEL TECNICO','NOMBRE COMPLETO','APELLIDOS Y NOMBRES'])
        dep_key = campo(datos, ['DEPARTAMENTO'])
        doc = documento(datos.get(doc_key))
        if not doc:
            continue
        nombre = str(datos.get(name_key) or '').strip()
        departamento = str(datos.get(dep_key) or '').strip()
        indice.setdefault(doc, []).append((nombre, departamento))
    return indice


def _exponer_cruce(datos, estado):
    """Expone columnas visibles para auditar el cruce de personal.

    'Técnico beneficiario (Form)' guarda el nombre tal como lo escribió el técnico,
    'Técnico beneficiario' queda con el nombre oficial (cruce por documento) y
    'Cruce de personal' con el resultado (VERIFICADO, NO ENCONTRADO, DUPLICADO...).
    """
    original = datos.get('_PERSONAL_ORIGINAL') or {}
    datos['Técnico beneficiario (Form)'] = str(original.get('tecnico') or '').strip()
    datos['Documento del beneficiario (Form)'] = str(original.get('documento') or '').strip()
    datos['Cruce de personal'] = estado
    return datos


def completar_personal(datos, indice):
    doc_key = campo(datos, ['Documento del beneficiario','DOCUMENTO','DNI','Numero de documento','Documento de identidad'])
    name_key = campo(datos, ['Técnico beneficiario','TECNICO','Nombre del tecnico','Nombre del beneficiario'])
    dep_key = campo(datos, ['DEPARTAMENTO','Departamento del tecnico','DEPARTAMENTO (Form)'])
    doc = documento(datos.get(doc_key))
    datos.setdefault('_PERSONAL_ORIGINAL', {'documento': datos.get(doc_key, ''), 'tecnico': datos.get(name_key, ''), 'departamento': datos.get(dep_key, '')})
    if datos.get('_PERSONAL_CORRECCION_MANUAL'):
        datos['_PERSONAL_CRUCE'] = {'estado':'CORREGIDO MANUALMENTE','criterio':'DOCUMENTO','documento':doc,'fuente':'Corrección del gestor'}
        datos['VERIFICACIÓN PERSONAL'] = 'Corregido manualmente'
        return _exponer_cruce(datos, 'CORREGIDO MANUALMENTE')
    estado = 'SIN DOCUMENTO' if not doc else ''
    candidatos = indice.get(doc, []) if not estado else []
    identidades = {(normalizar(n), normalizar(d)) for n,d in candidatos}
    if not estado:
        estado = 'NO ENCONTRADO' if not candidatos else 'DOCUMENTO DUPLICADO' if len(identidades) != 1 else 'VERIFICADO'
    if estado == 'VERIFICADO':
        nombre, departamento = candidatos[0]
        if not nombre:
            estado = 'SIN NOMBRE EN PERSONAL'
        else:
            datos[name_key or 'Técnico beneficiario'] = nombre
            datos['Técnico beneficiario'] = nombre
            if departamento:
                datos['DEPARTAMENTO'] = departamento
                if dep_key and not dep_key.endswith('(Form)'):
                    datos[dep_key] = departamento
            else:
                estado = 'SIN DEPARTAMENTO EN PERSONAL'
    datos['VERIFICACIÓN PERSONAL'] = 'Verificado' if estado == 'VERIFICADO' else 'Pendiente de verificar'
    datos['_PERSONAL_CRUCE'] = {'estado': estado, 'criterio': 'DOCUMENTO', 'documento': doc, 'fuente': 'Dataper'}
    return _homologar(_exponer_cruce(datos, estado))


def presentar_beneficiario_dataper(datos, indice, solo_meta=False):
    """Vista estricta por documento; nunca reescribe históricos ni el formulario."""
    result=dict(datos)
    doc_key=campo(datos,['Documento del beneficiario','DOCUMENTO','DNI','Numero de documento','Documento de identidad'])
    doc=documento(datos.get(doc_key) or datos.get('Documento del beneficiario (Form)'))
    candidatos=indice.get(doc,[]) if doc else []
    nombres={}
    for nombre,_departamento in candidatos:
        nombre=str(nombre or '').strip()
        if nombre:nombres.setdefault(normalizar(nombre),nombre)
    if len(nombres)==1:
        nombre=next(iter(nombres.values()));estado='VERIFICADO'
    elif len(nombres)>1:
        nombre='DNI DUPLICADO EN DATAPER';estado='DOCUMENTO DUPLICADO'
    else:
        nombre='NO REGISTRADO EN DATAPER';estado='NO ENCONTRADO' if doc else 'SIN DOCUMENTO'
    original=datos.get('_PERSONAL_ORIGINAL') or {}
    result.setdefault('Técnico beneficiario (Form)',original.get('tecnico') or datos.get('Técnico beneficiario',''))
    result.setdefault('Documento del beneficiario (Form)',original.get('documento') or datos.get(doc_key,''))
    result['_DATAPER_BENEFICIARIO']=nombre
    result['_DATAPER_RESULTADO']={'documento':doc,'estado':estado,'fuente':'Dataper'}
    if not solo_meta:result['Técnico beneficiario']=nombre
    return result
