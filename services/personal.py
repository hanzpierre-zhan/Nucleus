"""Campos del maestro de personal y proyectos autorizados, sin reescribir históricos."""
from flask import session
from db import db
from models import Usuario
from services.recursos_flm import familia, FLM_NOMBRES, contexto_recursos
from services.utilidades import get_menu_proyectos

import re
import unicodedata
from datetime import date

# Departamentos del Perú (y la Provincia Constitucional del Callao).
DEPARTAMENTOS = ['Amazonas', 'Áncash', 'Apurímac', 'Arequipa', 'Ayacucho', 'Cajamarca', 'Callao', 'Cusco',
                 'Huancavelica', 'Huánuco', 'Ica', 'Junín', 'La Libertad', 'Lambayeque', 'Lima', 'Loreto',
                 'Madre de Dios', 'Moquegua', 'Pasco', 'Piura', 'Puno', 'San Martín', 'Tacna', 'Tumbes', 'Ucayali']


def _plano(texto):
    texto = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', texto).strip().lower()


_POR_PLANO = {_plano(d): d for d in DEPARTAMENTOS}
_POR_PLANO.update({'cuzco': 'Cusco', 'ancash': 'Áncash'})


def departamento(valor):
    """Nombre oficial del departamento ('JUNIN' → 'Junín'); '' si no es un departamento del Perú."""
    return _POR_PLANO.get(_plano(valor), '')


def celular(valor):
    """Celular de 9 dígitos, sin espacios ni signos ('988 142 044' → '988142044'; acepta +51 adelante)."""
    digitos = re.sub(r'\D', '', str(valor or ''))
    if len(digitos) == 11 and digitos.startswith('51'):
        digitos = digitos[2:]
    return digitos if re.fullmatch(r'9\d{8}', digitos) else ''


NOMBRES = {'ENTEL':'FLM - ENTEL','CLARO':'FLM - CLARO','INTEGRATEL':'FLM - INTEGRATEL','PEXT':'FLM - PEXT'}
PARTES_NOMBRE = ('PRIMER NOMBRE', 'SEGUNDO NOMBRE', 'APELLIDO PATERNO', 'APELLIDO MATERNO')
FICHA_PERSONAL = (*PARTES_NOMBRE, 'FECHA DE NACIMIENTO', 'USUARIO AUTIN', 'PROYECTO', 'CELULAR',
                  'CORREO CORPORATIVO', 'NÚMERO DE EMERGENCIA', 'CONTACTO DE EMERGENCIA',
                  'DEPARTAMENTO', 'PROVINCIA', 'DISTRITO', 'CARGO')

CARGOS_DATAPER = ('TÉCNICO JUNIOR', 'TÉCNICO DE TELECOMUNICACIONES', 'SUPERVISOR',
                  'PERSONAL EXTERNO', 'ADMINISTRATIVO')
_CARGOS_POR_NOMBRE = {_plano(cargo): cargo for cargo in CARGOS_DATAPER}
_CARGOS_POR_NOMBRE.update({
    'junior': 'TÉCNICO JUNIOR',
    'tecnico junion': 'TÉCNICO JUNIOR',
    'tecnico telecomunicaciones': 'TÉCNICO DE TELECOMUNICACIONES',
    'supervisor de operaciones': 'SUPERVISOR',
    'externo': 'PERSONAL EXTERNO',
})

_ALIAS_FICHA = {
    'FECHA DE NACIMIENTO': ('fecha nacimiento',),
    'USUARIO AUTIN': ('autin',),
    'CORREO CORPORATIVO': ('email corporativo', 'correo coorporativo'),
    'NÚMERO DE EMERGENCIA': ('numero emergencia', 'telefono de emergencia', 'telefono emergencia'),
    'CONTACTO DE EMERGENCIA': ('contacto emergencia',),
}


def presentar_ficha(datos):
    ficha = presentar(datos)
    por_nombre = {_plano(campo): valor for campo, valor in datos.items() if str(valor or '').strip()}
    for campo in FICHA_PERSONAL:
        if campo not in ficha:
            variantes = (_plano(campo), *_ALIAS_FICHA.get(campo, ()))
            ficha[campo] = next((por_nombre[nombre] for nombre in variantes if nombre in por_nombre), '')
    ficha['CARGO'] = _CARGOS_POR_NOMBRE.get(_plano(ficha['CARGO']), '')
    nombre_departamento = departamento(ficha['DEPARTAMENTO'])
    if nombre_departamento:
        ficha['DEPARTAMENTO'] = nombre_departamento
    nombre = str(datos.get('TECNICO') or '').strip()
    apellidos, coma, nombres = nombre.partition(',')
    if coma and ',' not in nombres:
        apellidos = apellidos.split()
        nombres = nombres.split()
        if 1 <= len(nombres) <= 2 and len(apellidos) == 2 and not any(
            parte.lower() in ('de', 'del', 'la', 'los', 'las', 'san', 'santa')
            for parte in (*nombres, *apellidos)
        ):
            valores = (nombres[0], nombres[1] if len(nombres) == 2 else '', *apellidos)
            for campo, valor in zip(PARTES_NOMBRE, valores):
                if campo not in datos and not ficha[campo]:
                    ficha[campo] = valor
    estado = 'Completo' if all(ficha[c] for c in ('PRIMER NOMBRE', 'APELLIDO PATERNO', 'APELLIDO MATERNO')) else 'Por revisar'
    ficha['REVISIÓN DEL NOMBRE'] = estado
    return ficha

def proyectos_permitidos():
    return [p.nombre for p in get_menu_proyectos(session.get('user_id'), session.get('rol')) if p.nombre in FLM_NOMBRES]

def configurar(columnas):
    columnas = [dict(c) for c in columnas]
    definiciones = {'PROYECTO':{'nombre':'PROYECTO','tipo':'lista','opciones':proyectos_permitidos()},
                    'ESTADO':{'nombre':'ESTADO','tipo':'lista','opciones':['ACTIVO','CESADO']},
                    'DEPARTAMENTO':{'nombre':'DEPARTAMENTO','tipo':'lista','opciones':DEPARTAMENTOS},
                    'SUPERVISOR':{'nombre':'SUPERVISOR','tipo':'texto'}}
    for campo in FICHA_PERSONAL:
        definiciones.setdefault(campo, {'nombre': campo, 'tipo': 'texto'})
    for nombre,definicion in definiciones.items():
        existente = next((c for c in columnas if c.get('nombre') == nombre), None)
        if existente is not None: existente.update(definicion)
        else: columnas.append(definicion)
    return columnas

def presentar(datos):
    datos = dict(datos)
    if datos.get('PROYECTO'):
        datos['PROYECTO'] = NOMBRES.get(familia(datos['PROYECTO']), datos['PROYECTO'])
    datos.setdefault('SUPERVISOR','')
    return datos

def validar(datos, nuevo=False):
    datos = dict(datos)
    fecha = str(datos.get('FECHA DE NACIMIENTO') or '').strip()
    if fecha:
        from services.utilidades import ahora_peru
        try:
            nacimiento = date.fromisoformat(fecha)
        except ValueError:
            raise ValueError('Selecciona una fecha de nacimiento válida.') from None
        if not date(1900, 1, 1) <= nacimiento <= ahora_peru().date():
            raise ValueError('La fecha de nacimiento debe estar entre 1900 y hoy.')
        datos['FECHA DE NACIMIENTO'] = nacimiento.isoformat()
    correo = str(datos.get('CORREO CORPORATIVO') or '').strip()
    if correo:
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo):
            raise ValueError('Escribe un correo corporativo válido.')
        datos['CORREO CORPORATIVO'] = correo
    permitidos = proyectos_permitidos()
    if nuevo or 'PROYECTO' in datos:
        ctx = contexto_recursos()
        proyecto = datos.get('PROYECTO') or (ctx['flm_nombre'] if ctx else '')
        if not proyecto and len(permitidos)==1: proyecto=permitidos[0]
        proyecto = NOMBRES.get(familia(proyecto),'')
        if proyecto not in permitidos:
            raise ValueError('Selecciona uno de tus proyectos autorizados para registrar al personal.')
        datos['PROYECTO']=proyecto
    if 'ESTADO' in datos:
        estado = str(datos['ESTADO'] or '').strip().upper()
        if estado not in ('ACTIVO','CESADO'):
            raise ValueError('Selecciona Activo o Cesado.')
        datos['ESTADO']=estado
    if 'DEPARTAMENTO' in datos and str(datos['DEPARTAMENTO'] or '').strip():
        nombre = departamento(datos['DEPARTAMENTO'])
        if not nombre:
            raise ValueError('Selecciona un departamento del Perú.')
        datos['DEPARTAMENTO'] = nombre
    if 'CELULAR' in datos and str(datos['CELULAR'] or '').strip():
        numero = celular(datos['CELULAR'])
        if not numero:
            raise ValueError('El celular debe tener 9 dígitos y empezar con 9, sin espacios.')
        datos['CELULAR'] = numero
    if nuevo and session.get('rol') in ('gestor','supervisor'):
        usuario=db.session.get(Usuario,session.get('user_id'))
        datos['SUPERVISOR']=(usuario.nombre or usuario.username) if usuario else ''
    return datos
