"""Nombres de presentación: los identificadores de auditoría permanecen intactos."""
from flask import request, has_app_context, has_request_context
from models import Usuario


def nombres_usuarios():
    if not has_app_context():
        return {}
    cache = request.environ if has_request_context() else {}
    if 'nucleus.nombres_presentacion' not in cache:
        cache['nucleus.nombres_presentacion'] = {u.username: (u.nombre or u.username) for u in Usuario.query.all()}
    return cache['nucleus.nombres_presentacion']


def nombre_usuario(valor):
    return nombres_usuarios().get(str(valor or ''), valor or '')
