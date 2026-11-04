"""Corrige la clave de Claro sin cambiar ni eliminar registros."""
import json
from db import db
from models import Proyecto, AppConfig

VERSION = 'claro_ticket_id_v1'


def instalar():
    p = Proyecto.query.filter_by(nombre='FLM - CLARO').with_for_update().first()
    if not p or AppConfig.query.filter_by(proyecto_id=p.id, clave=VERSION).first():
        return
    pk = AppConfig.query.filter_by(proyecto_id=p.id, clave='primary_key').first()
    db.session.add(AppConfig(proyecto_id=p.id, clave=VERSION+'_backup', valor=json.dumps({'primary_key':pk.valor if pk else None})))
    if pk:
        pk.valor = 'Ticket Id'
    else:
        db.session.add(AppConfig(proyecto_id=p.id, clave='primary_key', valor='Ticket Id'))
    db.session.add(AppConfig(proyecto_id=p.id, clave=VERSION, valor='ok'))
    db.session.commit()
