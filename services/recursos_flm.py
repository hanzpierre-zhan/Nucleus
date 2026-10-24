"""Contexto explícito de los catálogos de cada FLM, sin duplicar sus datos."""
import json
import re
from services.normalizacion import normalizar
from flask import session
from db import db
from models import Proyecto,NucleusData
from services.utilidades import get_menu_proyectos

FLM_NOMBRES=('FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO','FLM - PEXT')


def familia(nombre):
    n=normalizar(nombre)
    if n in ('flm','flmentel','entel'): return 'ENTEL'
    if n in ('pext','flmpext','entelpext','flmentelpext'): return 'PEXT'
    if n in ('flmclaro','claro'): return 'CLARO'
    if n in ('flmintegratel','integratel'): return 'INTEGRATEL'
    return ''

def contexto_recursos():
    ctx=session.get('flm_resource_context')
    if not isinstance(ctx,dict) or ctx.get('catalogo_id')!=session.get('current_proyecto_id'): return None
    origen=db.session.get(Proyecto,ctx.get('flm_id'))
    if not origen or origen.nombre not in FLM_NOMBRES: return None
    if not any(p.id==origen.id for p in get_menu_proyectos(session.get('user_id'),session.get('rol'))): return None
    return {**ctx,'flm_nombre':origen.nombre,'familia':familia(origen.nombre)}

def familias_permitidas():
    return {familia(p.nombre) for p in get_menu_proyectos(session.get('user_id'),session.get('rol')) if familia(p.nombre)}

def filtrar_catalogo(datos):
    ctx=contexto_recursos()
    familias={ctx['familia']} if ctx else familias_permitidas()
    filtrados = [d for d in datos if familia(d.get('PROYECTO') or d.get('Proyecto')) in familias]
    return [{**d, ('Proyecto' if 'Proyecto' in d else 'PROYECTO'): ctx['flm_nombre']} for d in filtrados] if ctx else filtrados

def validar_fila_catalogo(datos):
    return familia(datos.get('PROYECTO') or datos.get('Proyecto')) in ({contexto_recursos()['familia']} if contexto_recursos() else familias_permitidas())
