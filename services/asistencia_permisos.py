"""Autorización de asistencia: permisos actuales y proyectos seleccionados."""

from flask import abort, request, session
from db import db
from models import Usuario, CuentaEspacio
from services import espacios
from services.utilidades import get_menu_proyectos


def ambitos():
    usuario = db.session.get(Usuario, session.get("user_id"))
    if usuario is None:
        abort(401)
    todos = {p.id: p for p in espacios.proyectos()}
    if usuario.rol in ("zeno", "suport"):
        return (todos, set(todos))
    if db.session.get(CuentaEspacio, usuario.id):
        lectura = espacios.ids_permitidos("personal")
        escritura = (
            espacios.ids_permitidos("personal", "editar")
            if usuario.rol in ("gestor", "supervisor", "contrata")
            else set()
        )
    else:
        menu = get_menu_proyectos(usuario.id, usuario.rol)
        if not any((p.nombre == "Dataper" for p in menu)):
            return ({}, set())
        lectura = {p.id for p in menu if p.id in todos}
        escritura = lectura if usuario.rol in ("gestor", "supervisor", "contrata") else set()
    return ({k: p for k, p in todos.items() if k in lectura}, escritura)


def seleccion():
    permitidos, escritura = ambitos()
    valor = request.args.get("proyecto", "todos")
    if not permitidos:
        abort(403)
    if valor == "todos":
        return (permitidos, escritura)
    try:
        pid = int(valor)
    except (ValueError, TypeError):
        abort(400)
    if pid not in permitidos:
        abort(403)
    return ({pid: permitidos[pid]}, escritura & {pid})
