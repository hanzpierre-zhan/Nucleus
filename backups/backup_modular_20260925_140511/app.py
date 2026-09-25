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
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException

from db import db
from config import Config, get_default_config

mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('font/ttf', '.ttf')


# ─────────────────────────────────────────────────────────────────────────────
# Registro de error handlers
# ─────────────────────────────────────────────────────────────────────────────
def _register_error_handlers(app):
    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        return jsonify(error=str(e)), 500


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
    from blueprints.cotizacion import bp as cotizacion_bp

    for _bp in (auth_bp, pages_bp, admin_bp, imports_bp, master_bp,
                rows_bp, wo_bp, evidencia_bp, cotizacion_bp):
        app.register_blueprint(_bp)


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────
def create_app(config_object=None):
    """Construye la app con la configuración indicada (útil para tests)."""
    config = config_object or get_default_config()
    app = Flask(__name__)
    app.config.from_object(config)
    app.config['SQLALCHEMY_DATABASE_URI'] = config.get_sqlalchemy_uri()

    os.makedirs(app.config['EVIDENCIA_DIR'], exist_ok=True)

    _register_error_handlers(app)
    _register_compress(app)

    db.init_app(app)
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