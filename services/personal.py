"""Campos del maestro de personal y proyectos autorizados, sin reescribir históricos."""
from flask import session
from db import db
from models import Usuario
from services.recursos_flm import familia, FLM_NOMBRES, contexto_recursos
from services.utilidades import get_menu_proyectos

NOMBRES = {'ENTEL':'FLM - ENTEL','CLARO':'FLM - CLARO','INTEGRATEL':'FLM - INTEGRATEL','PEXT':'FLM - PEXT'}

def proyectos_permitidos():
    return [p.nombre for p in get_menu_proyectos(session.get('user_id'), session.get('rol')) if p.nombre in FLM_NOMBRES]

def configurar(columnas):
    columnas = [dict(c) for c in columnas]
    definiciones = {'PROYECTO':{'nombre':'PROYECTO','tipo':'lista','opciones':proyectos_permitidos()},
                    'ESTADO':{'nombre':'ESTADO','tipo':'lista','opciones':['ACTIVO','CESADO']},
                    'SUPERVISOR':{'nombre':'SUPERVISOR','tipo':'texto'}}
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
    if nuevo and session.get('rol') in ('gestor','supervisor'):
        usuario=db.session.get(Usuario,session.get('user_id'))
        datos['SUPERVISOR']=(usuario.nombre or usuario.username) if usuario else ''
    return datos
