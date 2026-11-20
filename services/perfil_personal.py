"""Datos personales: no se deducen apellidos de nombres antiguos."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from db import db
from models import DatosPersonalesUsuario, Usuario

CAMPOS = ('primer_nombre', 'segundo_nombre', 'apellido_paterno', 'apellido_materno')


def hoy_lima():
    return datetime.now(ZoneInfo('America/Lima')).date()


def datos_perfil(usuario):
    perfil = db.session.get(DatosPersonalesUsuario, usuario.id)
    return ({**{c: getattr(perfil, c) for c in CAMPOS},
             'fecha_nacimiento': perfil.fecha_nacimiento.isoformat()} if perfil else {})


def guardar_perfil(usuario, datos):
    if not isinstance(datos, dict):
        raise ValueError('Revisa los datos personales.')
    valores = {}
    for campo in CAMPOS:
        valor = datos.get(campo, '')
        if not isinstance(valor, str):
            raise ValueError('Revisa los nombres y apellidos.')
        valor = ' '.join(valor.split())
        if len(valor) > 60 or (campo != 'segundo_nombre' and not valor):
            raise ValueError('Completa el primer nombre y ambos apellidos (máximo 60 caracteres por campo).')
        valores[campo] = valor
    if len(' '.join(v for v in valores.values() if v)) > 100:
        raise ValueError('El nombre completo no debe superar los 100 caracteres.')
    try:
        nacimiento = date.fromisoformat(datos.get('fecha_nacimiento', ''))
    except (ValueError, TypeError):
        raise ValueError('Ingresa una fecha de nacimiento válida.')
    if nacimiento > hoy_lima() or nacimiento.year < 1900:
        raise ValueError('La fecha de nacimiento debe estar entre 1900 y hoy.')
    perfil = db.session.get(DatosPersonalesUsuario, usuario.id)
    if perfil is None:
        perfil = DatosPersonalesUsuario(usuario_id=usuario.id)
        db.session.add(perfil)
    for campo, valor in valores.items():
        setattr(perfil, campo, valor)
    perfil.fecha_nacimiento = nacimiento
    usuario.nombre = ' '.join(v for v in valores.values() if v)


def cumpleaneros():
    from services.usuarios import usuarios_activos
    hoy = hoy_lima()
    return [{'id': u.id, 'nombre': u.nombre} for u, p in
            usuarios_activos().join(DatosPersonalesUsuario, DatosPersonalesUsuario.usuario_id == Usuario.id)
            .add_entity(DatosPersonalesUsuario).order_by(Usuario.nombre).all()
            if (p.fecha_nacimiento.month, p.fecha_nacimiento.day) == (hoy.month, hoy.day)]
