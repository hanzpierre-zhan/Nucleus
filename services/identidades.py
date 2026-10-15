"""Nombres de presentación: los identificadores de auditoría permanecen intactos."""
from flask import g, has_app_context
from models import Usuario


def nombres_usuarios():
    if not has_app_context():
        return {}
    if not hasattr(g, '_nombres_presentacion'):
        g._nombres_presentacion = {u.username: (u.nombre or u.username) for u in Usuario.query.all()}
    return g._nombres_presentacion


def nombre_usuario(valor):
    return nombres_usuarios().get(str(valor or ''), valor or '')
