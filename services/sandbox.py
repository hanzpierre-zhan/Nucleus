"""Bloqueo de salidas de red para el proceso local de pruebas exclusivamente."""
import ipaddress
import socket


def instalar_bloqueo_red():
    if getattr(socket.socket, '_nucleus_sandbox', False):
        return
    conectar = socket.socket.connect
    conectar_ex = socket.socket.connect_ex
    resolver = socket.getaddrinfo

    def permitido(direccion):
        if not isinstance(direccion, tuple):
            raise PermissionError('Red deshabilitada en el entorno de pruebas.')
        host = direccion[0]
        if host == 'localhost':
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise PermissionError('Destino externo bloqueado en el entorno de pruebas.')

    def connect(self, direccion):
        permitido(direccion)
        return conectar(self, direccion)

    def connect_ex(self, direccion):
        permitido(direccion)
        return conectar_ex(self, direccion)

    def getaddrinfo(host, *args, **kwargs):
        permitido((host, 0))
        return resolver(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    socket.socket._nucleus_sandbox = True


def instalar_guardas_http(app):
    from flask import abort, request

    @app.before_request
    def bloquear_integraciones():
        if request.path.startswith(('/api/rendicion/sync', '/api/admin/od_', '/api/import/')):
            abort(403, 'Integración externa deshabilitada en pruebas.')

    @app.after_request
    def recursos_locales(respuesta):
        # Los datos pueden contener enlaces; no cargar archivos remotos ni iframes.
        respuesta.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-src 'none'; object-src 'none'; "
            "form-action 'self'; base-uri 'self'")
        return respuesta
