"""Estructuras de columnas de Modus y Anton, sin copiar registros ni accesos."""
import json
from pathlib import Path
from models import Proyecto, AppConfig
from db import db

VERSION='columnas_fuente_20261016_v1'


def instalar():
    perfiles=json.loads((Path(__file__).parent/'data'/'columnas_flm_v1.json').read_text(encoding='utf-8'))
    for nombre,perfil in perfiles.items():
        proyecto=Proyecto.query.filter_by(nombre=nombre).first()
        if not proyecto:
            proyecto=Proyecto(nombre=nombre,icono='fa-network-wired' if nombre=='FLM - PEXT' else 'fa-folder-open')
            db.session.add(proyecto);db.session.flush()
        marca=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=VERSION).first()
        if marca:
            continue
        # Configuración anterior recuperable; no se modifica ninguna fila de datos.
        anteriores={}
        for clave,valor in perfil['configuracion'].items():
            cfg=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=clave).first()
            if cfg: anteriores[clave]=cfg.valor
            else:
                cfg=AppConfig(proyecto_id=proyecto.id,clave=clave);db.session.add(cfg)
            cfg.valor=valor if isinstance(valor,str) else json.dumps(valor,ensure_ascii=False)
        respaldo=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=VERSION+'_respaldo').first()
        if respaldo:
            respaldo.valor=json.dumps(anteriores,ensure_ascii=False)
        else:
            db.session.add(AppConfig(proyecto_id=proyecto.id,clave=VERSION+'_respaldo',valor=json.dumps(anteriores,ensure_ascii=False)))
        db.session.add(AppConfig(proyecto_id=proyecto.id,clave=VERSION,valor=perfil['origen']))
    db.session.commit()


def presentar(datos,proyecto,key):
    """Dar valor a las columnas equivalentes sin renombrar claves históricas."""
    if proyecto=='FLM - INTEGRATEL':
        aliases={'Task Id':['Número de WO','Numero de WO'], 'Createtime':['Fecha de creación (WO Creation date)'],
                 'Task Status':['Estado de la tarea (WO State)'], 'Site Id':['Código Site'],
                 'Site Id Name':['Nombre de Site'], 'Site Priority':['Prioridad del Site'],
                 'DEPARTAMENTO':['Departamento'],'Task Type':['Tipo tarea'], 'Current Phase':['Operate Phase']}
    elif proyecto=='FLM - PEXT':
        aliases={'Numero de WO':['Número de WO'], 'Estado de la tarea':['Estado de la tarea (WO State)'],
                 'Fecha de creacion':['Fecha de creación (WO Creation date)'], 'Causa raiz':['Causa raíz']}
    else:
        return datos
    result=dict(datos)
    for destino,fuentes in aliases.items():
        if not str(result.get(destino) or '').strip():
            result[destino]=next((result[f] for f in fuentes if str(result.get(f) or '').strip()),'')
    result.setdefault('Task Id' if proyecto=='FLM - INTEGRATEL' else 'Numero de WO',key)
    # El identificador también puede existir vacío en datos importados antiguos.
    campo='Task Id' if proyecto=='FLM - INTEGRATEL' else 'Numero de WO'
    if not result.get(campo):result[campo]=key
    return result
