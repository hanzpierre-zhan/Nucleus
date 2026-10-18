"""Nombres de proyecto compartidos por Material, Sites y Generadores."""
from services.personal import NOMBRES, proyectos_permitidos
from services.recursos_flm import familia, contexto_recursos

CATALOGOS = ('Material', 'SITE', 'Generadores')

def configurar(columnas):
    columnas=[dict(c) for c in columnas]
    definicion={'nombre':'PROYECTO','tipo':'lista','opciones':proyectos_permitidos()}
    existente=next((c for c in columnas if c.get('nombre')=='PROYECTO'),None)
    if existente is None:columnas.append(definicion)
    else:existente.update(definicion)
    return columnas

def presentar(datos):
    datos=dict(datos)
    valor=datos.get('PROYECTO')
    datos['PROYECTO']=NOMBRES.get(familia(valor),valor or '')
    return datos

def validar(datos,nuevo=False):
    datos=dict(datos)
    if nuevo or 'PROYECTO' in datos:
        permitidos=proyectos_permitidos()
        ctx=contexto_recursos()
        valor=datos.get('PROYECTO') or (ctx['flm_nombre'] if ctx else '')
        if not valor and len(permitidos)==1:valor=permitidos[0]
        nombre=NOMBRES.get(familia(valor),'')
        if nombre not in permitidos:raise ValueError('Selecciona uno de tus proyectos autorizados.')
        datos['PROYECTO']=nombre
    return datos
