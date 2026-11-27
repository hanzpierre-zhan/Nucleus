"""Actualización de la ficha propia desde Nucleus Mobile."""
import json
import re
from datetime import date

from db import db
from services import asistencia_movil, personal
from services.formularios_prueba import valor
from services.recursos_flm import familia

VERSION = 1
CAMPOS = (*personal.PARTES_NOMBRE, 'FECHA DE NACIMIENTO', 'USUARIO AUTIN',
          'CARGO', 'SUPERVISOR', 'CELULAR', 'CORREO CORPORATIVO',
          'NÚMERO DE EMERGENCIA', 'CONTACTO DE EMERGENCIA',
          'DEPARTAMENTO', 'PROVINCIA', 'DISTRITO')
REQUERIDOS = set(CAMPOS) - {'SEGUNDO NOMBRE', 'USUARIO AUTIN', 'CORREO CORPORATIVO'}


def leer(fila):
    try:
        datos = json.loads(fila.data_json or '{}') if fila else {}
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def es_supervisor(datos):
    cargo = personal._plano(valor(datos, 'CARGO'))
    return bool(re.match(r'^supervisora?\b', cargo))


def requiere_asistencia(datos):
    return personal.cargo_homologado(valor(datos, 'CARGO')) in personal.CARGOS_ASISTENCIA


def valores(datos):
    ficha = personal.presentar_ficha(datos)
    campos = {campo: ficha.get(campo) or valor(datos, campo) for campo in CAMPOS}
    if es_supervisor(datos):
        campos['CARGO'] = 'SUPERVISOR'
    return campos


def opciones(datos):
    proyecto = familia(valor(datos, 'PROYECTO'))
    supervisores = {
        ' '.join(str(valor(d, 'TECNICO')).split()).upper()
        for _, d in asistencia_movil._dataper()
        if proyecto and familia(valor(d, 'PROYECTO')) == proyecto and es_supervisor(d)
        and str(valor(d, 'ESTADO')).strip().upper() == 'ACTIVO' and valor(d, 'TECNICO')
    }
    actual = ' '.join(str(valor(datos, 'SUPERVISOR')).split()).upper()
    if actual:
        coincidencias = [nombre for nombre in supervisores if personal._plano(nombre).startswith(personal._plano(actual) + ' ')]
        if not coincidencias:
            supervisores.add(actual)
    return {
        'CARGO': ['SUPERVISOR'] if es_supervisor(datos) else [c for c in personal.CARGOS_DATAPER if c != 'SUPERVISOR'],
        'SUPERVISOR': sorted(supervisores),
        'DEPARTAMENTO': [d.upper() for d in personal.DEPARTAMENTOS],
    }


def guardar(fila, datos, opciones, foto):
    actuales = leer(fila)
    campos = {campo: ' '.join(datos[campo].split()).upper() for campo in CAMPOS}
    requeridos = REQUERIDOS - ({'SUPERVISOR'} if not opciones['SUPERVISOR'] or es_supervisor(actuales) else set())
    for campo in CAMPOS:
        if (campo in requeridos and not campos[campo]) or len(campos[campo]) > 120:
            raise ValueError(f'Revisa el campo {campo.lower()}.')
    if campos['CARGO'] not in opciones['CARGO']:
        raise ValueError('Selecciona un cargo de la lista.')
    if campos['SUPERVISOR'] and campos['SUPERVISOR'] not in opciones['SUPERVISOR']:
        raise ValueError('Selecciona un supervisor de la lista.')
    if not re.fullmatch(r'\+?[\d(). -]+', campos['NÚMERO DE EMERGENCIA']) or not any(
            c.isdigit() for c in campos['NÚMERO DE EMERGENCIA']):
        raise ValueError('Ingresa un número de emergencia válido.')
    campos['CELULAR'] = personal.celular(campos['CELULAR'])
    if not campos['CELULAR']:
        raise ValueError('El celular debe tener 9 dígitos y empezar con 9.')
    campos = personal.validar(campos)
    campos['DEPARTAMENTO'] = campos['DEPARTAMENTO'].upper()
    for campo, contenido in campos.items():
        if campo == 'CARGO' and es_supervisor(actuales):
            continue
        for alias in list(actuales):
            if alias != campo and alias.strip().casefold() == campo.casefold():
                del actuales[alias]
        actuales[campo] = contenido
    if foto and foto.filename or not actuales.get('_foto_perfil_mobile'):
        actuales['_foto_perfil_mobile'] = asistencia_movil.guardar_foto_perfil(foto)
    personal.con_nombre(actuales)
    actuales['_perfil_mobile_version'] = VERSION
    fila.data_json = json.dumps(actuales, ensure_ascii=False)
    db.session.commit()
