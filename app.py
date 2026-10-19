# -*- coding: utf-8 -*-
"""Punto de entrada de Nucleus (factory + instancia a nivel de módulo).

`gunicorn app:app` (Procfile) y `python app.py` funcionan sin cambios
gracias al `app = create_app()` a nivel de módulo.

Estructura del proyecto:
  app.py          ← composición y arranque
  infrastructure/ ← HTTP y registro de módulos
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
import mimetypes
from flask import Flask

try:
    from db import db
except ImportError as error:
    # Solo el arranque directo en Windows puede usar el entorno local verificado.
    # Las importaciones de servidor y pruebas mantienen sus errores originales.
    import sys
    from pathlib import Path

    local_python = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    blocked = any(
        text in str(error).lower()
        for text in (
            "control de aplicaciones",
            "application control",
        )
    )
    if (
        __name__ == "__main__"
        and sys.platform == "win32"
        and blocked
        and local_python.is_file()
        and Path(sys.executable).resolve() != local_python.resolve()
    ):
        import subprocess

        print(
            "Windows bloqueó una dependencia de este Python. Iniciando Nucleus con .venv…",
            flush=True,
        )
        try:
            result = subprocess.call(
                [str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                cwd=str(Path(__file__).resolve().parent),
            )
        except KeyboardInterrupt:
            result = 130
        raise SystemExit(result)
    raise
from config import Config, get_default_config
from infrastructure.http import (
    _pagina_error_http,
    _register_error_handlers,
    _register_compress,
    _register_no_cache_html,
)
from infrastructure.blueprints import _register_blueprints

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")


# ─────────────────────────────────────────────────────────────────────────────
# Invalidación del cache de "opciones del Detalle" (ver blueprints/wo.py)
# ─────────────────────────────────────────────────────────────────────────────
def _on_commit(*_args, **_kwargs):
    from flask import request, has_request_context

    if has_request_context():
        request.environ.pop("nucleus.menu_proyectos_cache", None)
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

    if getattr(_register_opciones_cache_invalidation, "_hecho", False):
        return
    try:
        event.listen(db.session, "after_commit", _on_commit)
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
    app.config["SQLALCHEMY_DATABASE_URI"] = config.get_sqlalchemy_uri()
    # connect_args de Postgres (connect_timeout) no existen en sqlite3;
    # se retiran cuando la URI es SQLite (desarrollo/tests locales).
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        _opts = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
        _opts.pop("connect_args", None)
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _opts

    os.makedirs(app.config["EVIDENCIA_DIR"], exist_ok=True)

    _register_error_handlers(app)
    _register_compress(app)
    _register_no_cache_html(app)

    db.init_app(app)
    from services.alcance_proyectos import instalar as instalar_alcance_proyectos
    instalar_alcance_proyectos()
    _register_opciones_cache_invalidation()
    _register_blueprints(app)
    from services.legacy_columns import install, clean_existing_config

    install()

    # Migraciones de base de datos (idempotentes)
    from migrations import run_migrations

    database_url = os.environ.get("DATABASE_URL", "")
    run_migrations(app, database_url)
    with app.app_context():
        from services.columnas_fuente import instalar as instalar_columnas_fuente

        instalar_columnas_fuente()
        from services.form_options import instalar_pext

        instalar_pext()
        clean_existing_config()
        from services.liquidacion_numero import numerar_historicos

        numerar_historicos()

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Instancia a nivel de módulo (compatible con `gunicorn app:app`)
# ─────────────────────────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5001)))
