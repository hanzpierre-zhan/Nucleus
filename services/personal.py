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
                  'DEPARTAMENTO', 'PROVINCIA', 'DISTRITO', 'CARGO', 'CONTRATA')

CARGOS_ASISTENCIA = ('TÉCNICO JUNIOR', 'TÉCNICO ESPECIALISTA')
CARGOS_DATAPER = (*CARGOS_ASISTENCIA, 'SUPERVISOR',
                  'PERSONAL EXTERNO', 'ADMINISTRATIVO')
_CARGOS_POR_NOMBRE = {_plano(cargo): cargo for cargo in CARGOS_DATAPER}
_CARGOS_POR_NOMBRE.update({
    'junior': 'TÉCNICO JUNIOR',
    'tecnico junion': 'TÉCNICO JUNIOR',
    'tecnico telecomunicaciones': 'TÉCNICO ESPECIALISTA',
    'tecnico de telecomunicaciones': 'TÉCNICO ESPECIALISTA',
    'especialista': 'TÉCNICO ESPECIALISTA',
    'supervisor de operaciones': 'SUPERVISOR',
    'externo': 'PERSONAL EXTERNO',
})


def cargo_homologado(valor):
    return _CARGOS_POR_NOMBRE.get(_plano(valor), '')

_ALIAS_FICHA = {
    'FECHA DE NACIMIENTO': ('fecha nacimiento',),
    'USUARIO AUTIN': ('autin',),
    'CORREO CORPORATIVO': ('email corporativo', 'correo coorporativo'),
    'NÚMERO DE EMERGENCIA': ('numero emergencia', 'telefono de emergencia', 'telefono emergencia'),
    'CONTACTO DE EMERGENCIA': ('contacto emergencia',),
}

_NOMBRES_FRECUENTES = frozenset("""
    alex alejandro alberto ana andres angel antonio carlos carmen cesar christian cristhian
    daniel david diego edgar eduardo edwuards elena eloy emilio enrique fernando francisco
    frank gabriel gerardo gloria hugo isabel javier jesus jorge jose juan julio karla
    laura luis manuel marco maria mario miguel monica oscar pablo paola paolo patricia
    pedro rafael raul renato ricardo roberto rosa ruben sandra sergio silvia victor wilber
""".split())
_PARTICULAS_NOMBRE = {'de', 'del', 'la', 'los', 'las', 'san', 'santa'}


def _desglosar_nombre(valor):
    original = str(valor or '').strip()
    izquierda, coma, derecha = original.partition(',')
    if coma:
        apellidos, nombres = izquierda.split(), derecha.split()
    else:
        tokens = original.split()
        if len(tokens) not in (3, 4):
            return ()
        inicio_nombre = _plano(tokens[0]) in _NOMBRES_FRECUENTES
        tercero_nombre = _plano(tokens[2]) in _NOMBRES_FRECUENTES
        if inicio_nombre == tercero_nombre:
            return ()
        if inicio_nombre:
            nombres, apellidos = tokens[:-2], tokens[-2:]
        else:
            apellidos, nombres = tokens[:2], tokens[2:]
    if (len(apellidos) != 2 or not 1 <= len(nombres) <= 2
            or any(not t.isalpha() or _plano(t) in _PARTICULAS_NOMBRE for t in (*nombres, *apellidos))):
        return ()
    return nombres[0], nombres[1] if len(nombres) == 2 else '', *apellidos


def presentar_ficha(datos):
    ficha = presentar(datos)
    por_nombre = {_plano(campo): valor for campo, valor in datos.items() if str(valor or '').strip()}
    for campo in FICHA_PERSONAL:
        if campo not in ficha:
            variantes = (_plano(campo), *_ALIAS_FICHA.get(campo, ()))
            ficha[campo] = next((por_nombre[nombre] for nombre in variantes if nombre in por_nombre), '')
    ficha['CARGO'] = cargo_homologado(ficha['CARGO'])
    nombre_departamento = departamento(ficha['DEPARTAMENTO'])
    if nombre_departamento:
        ficha['DEPARTAMENTO'] = nombre_departamento
    valores = _desglosar_nombre(datos.get('TECNICO'))
    for campo, valor in zip(PARTES_NOMBRE, valores):
        if campo not in datos and not ficha[campo]:
            ficha[campo] = valor
    ficha.pop('REVISIÓN DEL NOMBRE', None)
    ficha.pop('REVISION DEL NOMBRE', None)
    return ficha


def resolver_supervisores(fichas):
    from services.usuarios import usuarios_activos

    def partes(nombre):
        return frozenset(re.findall(r'[a-z]+', _plano(nombre)))

    usuarios = {}
    for usuario in usuarios_activos():
        nombre = str(usuario.nombre or '').strip()
        if len(partes(nombre)) >= 3:
            usuarios[partes(nombre)] = nombre
    padron = {}
    for ficha in fichas:
        opciones = [ficha.get('SUPERVISOR')]
        if _plano(ficha.get('CARGO')).startswith('supervisor'):
            opciones.append(ficha.get('TECNICO'))
        for nombre in opciones:
            nombre = str(nombre or '').strip()
            if len(partes(nombre)) >= 3:
                padron[partes(nombre)] = nombre

    def resolver(valor):
        clave = partes(valor)
        if not clave:
            return valor
        for nombres in (usuarios, padron):
            exacto = nombres.get(clave)
            if exacto:
                return exacto
            candidatos = [nombre for tokens, nombre in nombres.items() if clave <= tokens]
            if len(candidatos) == 1:
                return candidatos[0]
            if candidatos:
                break
        return valor

    return resolver

def proyectos_permitidos():
    return [p.nombre for p in get_menu_proyectos(session.get('user_id'), session.get('rol')) if p.nombre in FLM_NOMBRES]

def configurar(columnas):
    columnas = [dict(c) for c in columnas]
    definiciones = {'PROYECTO':{'nombre':'PROYECTO','tipo':'lista','opciones':proyectos_permitidos()},
                    'ESTADO':{'nombre':'ESTADO','tipo':'lista','opciones':['ACTIVO','CESADO']},
                    'CARGO':{'nombre':'CARGO','tipo':'lista','opciones':list(CARGOS_DATAPER)},
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
    if 'CONTRATA' in datos:
        contrata = ' '.join(str(datos['CONTRATA'] or '').split())
        if re.sub(r'[^a-z0-9]', '', _plano(contrata)) in ('cobra', 'cobraperu', 'cobraperusa', 'cobraperusac'):
            datos['CONTRATA'] = 'COBRA'
        else:
            datos['CONTRATA'] = '' if contrata in ('-', '–', '—', '--') else contrata.upper()
    datos.setdefault('SUPERVISOR','')
    return datos

def validar(datos, nuevo=False):
    datos = dict(datos)
    if 'CARGO' in datos:
        datos['CARGO'] = cargo_homologado(datos['CARGO'])
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
