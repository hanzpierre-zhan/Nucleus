"""Retiro de cuentas sin destruir a los autores del historial operativo."""
import secrets

from sqlalchemy import or_
from werkzeug.security import generate_password_hash

from models import AccesoEspacio, AccesoProyecto, CuentaEspacio, Usuario

ROL_ELIMINADO = 'eliminado'


def usuarios_activos():
    return Usuario.query.filter(or_(Usuario.rol.is_(None), Usuario.rol != ROL_ELIMINADO))


def retirar_cuenta(usuario):
    """El llamador confirma la transacción; todas las FK de auditoría se conservan.

    Se reserva el identificador original: también hay campos históricos de
    autoría guardados como username, que no deben atribuirse a otra persona.
    """
    if usuario.rol == ROL_ELIMINADO:
        return
    AccesoProyecto.query.filter_by(usuario_id=usuario.id).delete(synchronize_session=False)
    AccesoEspacio.query.filter_by(usuario_id=usuario.id).delete(synchronize_session=False)
    CuentaEspacio.query.filter_by(usuario_id=usuario.id).delete(synchronize_session=False)
    usuario.nombre = usuario.nombre or usuario.username
    usuario.password_hash = generate_password_hash(secrets.token_urlsafe(64))
    usuario.rol = ROL_ELIMINADO
