"""Registro de módulos y contexto de las plantillas. Imports diferidos para evitar ciclos."""


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
    from blueprints.autin import bp as autin_bp
    from blueprints.evidencia import bp as evidencia_bp
    from blueprints.rendicion import bp as rendicion_bp
    from blueprints.cotizacion import bp as cotizacion_bp
    from blueprints.refacturable import bp as refacturable_bp
    from blueprints.recursos import bp as recursos_bp
    from blueprints.espacios import bp as espacios_bp
    from blueprints.asistencia import bp as asistencia_bp

    for _bp in (
        auth_bp,
        pages_bp,
        admin_bp,
        imports_bp,
        master_bp,
        rows_bp,
        wo_bp,
        autin_bp,
        evidencia_bp,
        rendicion_bp,
        cotizacion_bp,
        refacturable_bp,
        recursos_bp,
        espacios_bp,
        asistencia_bp,
    ):
        app.register_blueprint(_bp)
    app.register_blueprint(
        refacturable_bp, url_prefix="/liquidaciones", name="liquidaciones"
    )

    @app.context_processor
    def identidades():
        from flask import session

        if not session.get("user_id"):
            return {"nombres_usuarios": {}}
        from services.identidades import nombres_usuarios

        nombres = nombres_usuarios()
        return {
            "nombres_usuarios": nombres,
            "nombre_usuario_actual": nombres.get(
                session.get("username"), session.get("username")
            ),
        }

    @app.context_processor
    def recursos_contexto_template():
        from services.recursos_flm import contexto_recursos
        from services.alcance_proyectos import contexto

        alcance = contexto()
        return {"flm_resource_context": contexto_recursos(),
                "familias_acceso": sorted(alcance['familias']) if alcance is not None else ['ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT']}
