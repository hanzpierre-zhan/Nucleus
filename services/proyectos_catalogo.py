"""Nombres de proyecto compartidos por Material, Sites y Generadores."""
from services.personal import NOMBRES, proyectos_permitidos
from services.recursos_flm import familia, contexto_recursos

CATALOGOS = ('Material', 'SITE', 'Generadores')

def configurar(columnas):
    columnas=[dict(c) for c in columnas]
    definicion={'nombre':'PROYECTO','tipo':'lista','opciones':proyectos_permitidos()}
    existente=next((c for c in columnas if str(c.get('nombre','')).upper()=='PROYECTO'),None)
    if existente is None:columnas.append(definicion)
    else:
        definicion['nombre']=existente['nombre']
        existente.update(definicion)
    return columnas

def presentar(datos):
    datos=dict(datos)
    key='Proyecto' if 'Proyecto' in datos else 'PROYECTO'
    valor=datos.get(key)
    datos[key]=NOMBRES.get(familia(valor),valor or '')
    return datos

def validar(datos,nuevo=False):
    datos=dict(datos)
    key='Proyecto' if 'Proyecto' in datos else 'PROYECTO'
    if nuevo or key in datos:
        permitidos=proyectos_permitidos()
        ctx=contexto_recursos()
        valor=datos.get(key) or (ctx['flm_nombre'] if ctx else '')
        if not valor and len(permitidos)==1:valor=permitidos[0]
        nombre=NOMBRES.get(familia(valor),'')
        if nombre not in permitidos:raise ValueError('Selecciona uno de tus proyectos autorizados.')
        datos[key]=nombre
    return datos
