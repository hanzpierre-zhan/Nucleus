"""Claves del portal de técnicos, separadas de los registros de Dataper.

La clave inicial (y tras un restablecimiento) es el documento; en ese caso, o
cuando pasaron más de DIAS_VIGENCIA desde el último cambio, se exige crear una
nueva antes de usar el portal.
"""
import hmac
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from db import db
from models import ClaveTecnico

DIAS_VIGENCIA = 30
LARGO_MINIMO = 6


def verificar(documento, clave):
    registro = db.session.get(ClaveTecnico, documento)
    if registro is None:
        return hmac.compare_digest(str(documento), str(clave))
    return check_password_hash(registro.clave_hash, str(clave))


def debe_cambiar(documento, ahora=None):
    registro = db.session.get(ClaveTecnico, documento)
    if registro is None:
        return True
    return (ahora or datetime.utcnow()) - registro.cambiada_en > timedelta(days=DIAS_VIGENCIA)


def error_nueva(documento, actual, nueva, confirmar):
    if not verificar(documento, actual):
        return 'La clave actual no es correcta.'
    if len(nueva) < LARGO_MINIMO:
        return 'La nueva clave debe tener al menos %d caracteres.' % LARGO_MINIMO
    if nueva != confirmar:
        return 'La confirmación no coincide con la nueva clave.'
    if nueva == documento or nueva == actual:
        return 'La nueva clave no puede ser tu documento ni la clave actual.'
    return None


def cambiar(documento, nueva):
    registro = db.session.get(ClaveTecnico, documento)
    if registro is None:
        registro = ClaveTecnico(documento=documento)
        db.session.add(registro)
    registro.clave_hash = generate_password_hash(nueva)
    registro.cambiada_en = datetime.utcnow()
    db.session.commit()


def restablecer(documento):
    """Vuelve la clave al documento; el técnico deberá cambiarla al ingresar."""
    registro = db.session.get(ClaveTecnico, documento)
    if registro is not None:
        db.session.delete(registro)
