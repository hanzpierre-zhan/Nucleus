"""Entrada WSGI ligera: el puerto abre antes de las migraciones de la app.

El health check solo responde una vez que create_app termina correctamente.
La exclusión mutua impide inicializar/migrar varias veces con gthread.
"""
from threading import Lock

_application = None
_startup_lock = Lock()


def application(environ, start_response):
    global _application
    if _application is None:
        with _startup_lock:
            if _application is None:
                from app import app
                _application = app
    return _application(environ, start_response)
