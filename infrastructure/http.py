"""Errores, compresión y caché HTTP; sin reglas de negocio."""

import gzip
from flask import request, jsonify, Response, current_app
from werkzeug.exceptions import HTTPException


def _pagina_error_http(titulo, mensaje, codigo):
    """Página HTML mínima para errores que llegan al usuario de la UI web
    (404 de navegación, etc.). No depende de plantillas para no romper nada."""
    html = (
        '<!DOCTYPE html>\n<html lang="es">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s - Nucleus</title>\n"
        "<style>body{font-family:system-ui,Arial,sans-serif;background:#f5f5f7;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}"
        ".card{background:#fff;padding:2.5rem 3rem;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.08);"
        "text-align:center;max-width:420px;}h1{margin:0 0 .5rem;font-size:2.4rem;}"
        "p{color:#555;margin:0 0 1.2rem;}</style>\n"
        '</head>\n<body>\n<div class="card">\n'
        "<h1>%s</h1>\n<p>%s</p>\n"
        '<a href="#" onclick="history.back();return false;">Volver</a> | '
        '<a href="/">Ir al inicio</a>\n'
        "</div>\n</body>\n</html>\n"
    ) % (codigo, codigo, mensaje)
    return Response(html, status=codigo, mimetype="text/html")


def _register_error_handlers(app):
    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            # Las APIs (prefijo /api) mantienen el contrato JSON actual.
            # La navegación web recibe una página HTML amigable.
            if e.code == 404 and not request.path.startswith("/api"):
                return _pagina_error_http(
                    "Página no encontrada",
                    "La página o el recurso que buscas no existe.",
                    404,
                )
            return jsonify(error=e.description), e.code
        # Errores 500: loguear el traceback y NO filtrar str(e) al cliente.
        current_app.logger.exception("Error no controlado en %s", request.path)
        return jsonify(error="Error interno del servidor"), 500


def _register_compress(app):
    @app.after_request
    def _compress_response(response):
        try:
            if response.direct_passthrough:
                return response
            if response.status_code < 200 or response.status_code >= 300:
                return response
            if response.headers.get("Content-Encoding"):
                return response
            if "gzip" not in request.accept_encodings:
                return response
            ctype = (response.content_type or "").lower()
            if not any(
                t in ctype
                for t in (
                    "text/",
                    "application/json",
                    "application/javascript",
                    "application/xml",
                    "image/svg",
                )
            ):
                return response
            data = response.get_data()
            if len(data) < 1024:
                return response
            # Nivel adaptativo: comprimir a nivel 6 una respuesta grande (la
            # tabla FLM ronda los 9 MB) cuesta ~1 s de CPU en una instancia
            # pequeña. Para esos tamaños el nivel 3 obtiene casi el mismo
            # resultado con la mitad de CPU; las respuestas pequeñas siguen
            # usando el nivel 6.
            nivel = 3 if len(data) >= 1_000_000 else 6
            compressed = gzip.compress(data, nivel)
            if len(compressed) >= len(data):
                return response
            response.set_data(compressed)
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Content-Length"] = str(len(compressed))
            vary = response.headers.get("Vary")
            response.headers["Vary"] = (
                (vary + ", Accept-Encoding") if vary else "Accept-Encoding"
            )
        except Exception:
            pass
        return response


def _register_no_cache_html(app):
    @app.after_request
    def _no_cache_html(response):
        try:
            if response.mimetype == "text/html" and not response.headers.get(
                "Cache-Control"
            ):
                response.headers["Cache-Control"] = "no-cache"
        except Exception:
            pass
        return response
