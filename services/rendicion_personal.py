"""Cruce de nuevas solicitudes con el catálogo de Personal (Dataper)."""
import json
import re
import unicodedata
from models import Proyecto, NucleusData


def normalizar(valor):
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in unicodedata.normalize('NFKD', str(valor or '')).lower() if not unicodedata.combining(c)))


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


def completar_personal(datos, indice):
    doc_key = campo(datos, ['Documento del beneficiario','DOCUMENTO','DNI','Numero de documento','Documento de identidad'])
    name_key = campo(datos, ['Técnico beneficiario','TECNICO','Nombre del tecnico','Nombre del beneficiario'])
    dep_key = campo(datos, ['DEPARTAMENTO','Departamento del tecnico','DEPARTAMENTO (Form)'])
    doc = documento(datos.get(doc_key))
    datos.setdefault('_PERSONAL_ORIGINAL', {'documento': datos.get(doc_key, ''), 'tecnico': datos.get(name_key, ''), 'departamento': datos.get(dep_key, '')})
    if datos.get('_PERSONAL_CORRECCION_MANUAL'):
        datos['_PERSONAL_CRUCE'] = {'estado':'CORREGIDO MANUALMENTE','criterio':'DOCUMENTO','documento':doc,'fuente':'Corrección del gestor'}
        datos['VERIFICACIÓN PERSONAL'] = 'Corregido manualmente'
        return datos
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
    return datos
