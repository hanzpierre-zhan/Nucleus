# -*- coding: utf-8 -*-
"""Punto de entrada de Nucleus (factory + instancia a nivel de módulo).

`gunicorn app:app` (Procfile) y `python app.py` funcionan sin cambios
gracias al `app = create_app()` a nivel de módulo.

Estructura del proyecto:
  app.py          ← este archivo (≈80 líneas)
  config.py       ← configuración por entorno
  db.py           ← singleton SQLAlchemy
  models.py       ← modelos de base de datos
  migrations/     ← migraciones de arranque
  services/       ← lógica de negocio pura (sin rutas)
  blueprints/     ← rutas agrupadas por dominio
  templates/      ← plantillas Jinja2
  static/         ← archivos estáticos
"""
import os
import gzip
import mimetypes
from flask import Flask, request, jsonify, Response, current_app
from werkzeug.exceptions import HTTPException

from db import db
from config import Config, get_default_config

mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('font/ttf', '.ttf')


# ─────────────────────────────────────────────────────────────────────────────
# Registro de error handlers
# ─────────────────────────────────────────────────────────────────────────────
def _pagina_error_http(titulo, mensaje, codigo):
    """Página HTML mínima para errores que llegan al usuario de la UI web
    (404 de navegación, etc.). No depende de plantillas para no romper nada."""
    html = (
        '<!DOCTYPE html>\n<html lang="es">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>%s - Nucleus</title>\n'
        '<style>body{font-family:system-ui,Arial,sans-serif;background:#f5f5f7;'
        'display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}'
        '.card{background:#fff;padding:2.5rem 3rem;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.08);'
        'text-align:center;max-width:420px;}h1{margin:0 0 .5rem;font-size:2.4rem;}'
        'p{color:#555;margin:0 0 1.2rem;}</style>\n'
        '</head>\n<body>\n<div class="card">\n'
        '<h1>%s</h1>\n<p>%s</p>\n'
        '<a href="#" onclick="history.back();return false;">Volver</a> | '
        '<a href="/">Ir al inicio</a>\n'
        '</div>\n</body>\n</html>\n'
    ) % (codigo, codigo, mensaje)
    return Response(html, status=codigo, mimetype='text/html')


def _register_error_handlers(app):
    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            # Las APIs (prefijo /api) mantienen el contrato JSON actual.
            # La navegación web recibe una página HTML amigable.
            if e.code == 404 and not request.path.startswith('/api'):
                return _pagina_error_http(
                    'Página no encontrada',
                    'La página o el recurso que buscas no existe.',
                    404)
            return jsonify(error=e.description), e.code
        # Errores 500: loguear el traceback y NO filtrar str(e) al cliente.
        current_app.logger.exception('Error no controlado en %s', request.path)
        return jsonify(error='Error interno del servidor'), 500


# ─────────────────────────────────────────────────────────────────────────────
# Compresión gzip automática
# ─────────────────────────────────────────────────────────────────────────────
def _register_compress(app):
    @app.after_request
    def _compress_response(response):
        try:
            if response.direct_passthrough:
                return response
            if response.status_code < 200 or response.status_code >= 300:
                return response
            if response.headers.get('Content-Encoding'):
                return response
            if 'gzip' not in request.accept_encodings:
                return response
            ctype = (response.content_type or '').lower()
            if not any(t in ctype for t in (
                    'text/', 'application/json', 'application/javascript',
                    'application/xml', 'image/svg')):
                return response
            data = response.get_data()
            if len(data) < 1024:
                return response
            compressed = gzip.compress(data, 6)
            if len(compressed) >= len(data):
                return response
            response.set_data(compressed)
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = str(len(compressed))
            vary = response.headers.get('Vary')
            response.headers['Vary'] = (vary + ', Accept-Encoding') if vary else 'Accept-Encoding'
        except Exception:
            pass
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Las páginas HTML se revalidan siempre (así los cambios de plantilla/JS se
# reflejan en cuanto se actualiza el servidor, sin depender de la caché del navegador)
# ─────────────────────────────────────────────────────────────────────────────
def _register_no_cache_html(app):
    @app.after_request
    def _no_cache_html(response):
        try:
            if response.mimetype == 'text/html' and not response.headers.get('Cache-Control'):
                response.headers['Cache-Control'] = 'no-cache'
        except Exception:
            pass
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Registro de blueprints
# ─────────────────────────────────────────────────────────────────────────────
def _register_blueprints(app):
    # Los blueprints se importan aquí (dentro del contexto de app) para evitar
    # importaciones circulares. Cada uno define su propio prefijo de URL.
    from blueprints.auth import bp as auth_bp
    from blueprints.pages import bp as pages_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.imports import bp as imports_bp
    from blueprints.master import bp as master_bp
    from blueprints.rows import bp as rows_bp
    from blueprints.wo import bp as wo_bp
    from blueprints.evidencia import bp as evidencia_bp
    from blueprints.rendicion import bp as rendicion_bp
    from blueprints.cotizacion import bp as cotizacion_bp
    from blueprints.refacturable import bp as refacturable_bp

    for _bp in (auth_bp, pages_bp, admin_bp, imports_bp, master_bp,
                rows_bp, wo_bp, evidencia_bp, rendicion_bp, cotizacion_bp, refacturable_bp):
        app.register_blueprint(_bp)


# ─────────────────────────────────────────────────────────────────────────────
# Invalidación del cache de "opciones del Detalle" (ver blueprints/wo.py)
# ─────────────────────────────────────────────────────────────────────────────
def _on_commit(*_args, **_kwargs):
    try:
        from blueprints.wo import invalidar_opciones_cache
        invalidar_opciones_cache()
    except Exception:
        pass
    try:
        from blueprints.pages import invalidar_site_map_cache
        invalidar_site_map_cache()
    except Exception:
        pass


def _register_opciones_cache_invalidation():
    """Cada COMMIT (alta/edición/import de filas) recalcula la lista de opciones."""
    from sqlalchemy import event
    if getattr(_register_opciones_cache_invalidation, '_hecho', False):
        return
    try:
        event.listen(db.session, 'after_commit', _on_commit)
        _register_opciones_cache_invalidation._hecho = True
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────
def create_app(config_object=None):
    """Construye la app con la configuración indicada (útil para tests)."""
    config = config_object or get_default_config()
    app = Flask(__name__)
    app.config.from_object(config)
    app.config['SQLALCHEMY_DATABASE_URI'] = config.get_sqlalchemy_uri()
    # connect_args de Postgres (connect_timeout) no existen en sqlite3;
    # se retiran cuando la URI es SQLite (desarrollo/tests locales).
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        _opts = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})
        _opts.pop('connect_args', None)
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _opts
    
    os.makedirs(app.config['EVIDENCIA_DIR'], exist_ok=True)

    _register_error_handlers(app)
    _register_compress(app)
    _register_no_cache_html(app)

    db.init_app(app)
    _register_opciones_cache_invalidation()
    _register_blueprints(app)

    # Migraciones de base de datos (idempotentes)
    from migrations import run_migrations
    database_url = os.environ.get('DATABASE_URL', '')
    run_migrations(app, database_url)

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Instancia a nivel de módulo (compatible con `gunicorn app:app`)
# ─────────────────────────────────────────────────────────────────────────────
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5001)))