"""Asistencia por día marcada por la gestora/supervisor, con permisos frescos."""

import secrets
from datetime import date
from flask import Blueprint, abort, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from db import db
from models import AsistenciaDiaria
from services.utilidades import login_required, get_menu_proyectos, ahora_peru
from services.asistencia_permisos import ambitos, seleccion
from services.asistencia import (
    ConflictoVersion,
    guardar_marcas,
    ESTADOS,
    periodo_mensual,
    registros_periodo,
    filtrar_registros,
    resumir,
    consultar_dia,
    consultar_planilla,
)
from services.asistencia_exportacion import exportar

bp = Blueprint("asistencia", __name__)


def fecha_valida(valor):
    try:
        return date.fromisoformat(str(valor))
    except (ValueError, TypeError):
        abort(400, "Fecha inválida.")


@bp.before_request
def csrf():
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        token = session.get("asistencia_csrf", "")
        recibido = request.headers.get("X-Asistencia-CSRF", "")
        if not token or not secrets.compare_digest(token, recibido):
            abort(403)


@bp.route("/personal/asistencia")
@login_required
def index():
    permitidos, _ = ambitos()
    if not permitidos:
        abort(403)
    session.setdefault("asistencia_csrf", secrets.token_urlsafe(32))
    return render_template(
        "asistencia.html",
        proyectos_list=get_menu_proyectos(session["user_id"], session.get("rol")),
        hoy=ahora_peru().date().isoformat(),
    )


@bp.route("/api/asistencia/contexto")
@login_required
def contexto():
    ps, editables = ambitos()
    if not ps:
        abort(403)
    return jsonify(
        proyectos=[
            {"id": pid, "nombre": p.nombre, "editar": pid in editables}
            for pid, p in ps.items()
        ],
        estados=ESTADOS,
        hoy=ahora_peru().date().isoformat(),
    )


@bp.route("/api/asistencia/dia")
@login_required
def dia():
    ps, escritura = seleccion()
    fecha = fecha_valida(request.args.get("fecha", ahora_peru().date().isoformat()))
    return jsonify(
        fecha=fecha.isoformat(), registros=consultar_dia(ps, escritura, fecha)
    )


@bp.route("/api/asistencia/dia", methods=["POST"])
@login_required
def guardar():
    ps, escritura = seleccion()
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict) or not isinstance(datos.get("registros"), list):
        abort(400)
    fecha = fecha_valida(datos.get("fecha"))
    cambios = datos["registros"]
    if not cambios or len(cambios) > 500:
        abort(400)
    try:
        guardados = guardar_marcas(ps, escritura, fecha, cambios, session["user_id"])
        return jsonify(success=True, guardados=guardados)
    except ConflictoVersion as error:
        db.session.rollback()
        return jsonify(error=str(error)), 409
    except (ValueError, TypeError, KeyError) as error:
        db.session.rollback()
        return (jsonify(error=str(error)), 400)
    except (IntegrityError, StaleDataError):
        db.session.rollback()
        return (
            jsonify(
                error="La asistencia cambió durante el guardado. Actualiza y vuelve a intentar."
            ),
            409,
        )


@bp.route("/api/asistencia/mensual")
@login_required
def mensual():
    ps, _ = seleccion()
    inicio, fin, _ = periodo_mensual(request.args.get("mes", ""))
    filas = (
        registros_periodo(ps, inicio, fin)
        .order_by(AsistenciaDiaria.fecha, AsistenciaDiaria.nombre)
        .all()
    )
    filas = filtrar_registros(filas, ps, request.args.get("personal"))
    respuesta = exportar(request.args.get("formato"), filas, ps, inicio)
    if respuesta is not None:
        return respuesta
    return jsonify(
        mes=inicio.strftime("%Y-%m"),
        resumen=resumir(filas, ps),
        marcas=len(filas),
        aviso="Solo se cuentan días marcados; no se infieren faltas ni se calculan remuneraciones.",
    )


@bp.route("/api/asistencia/planilla")
@login_required
def planilla():
    ps, escritura = seleccion()
    inicio, fin, dias = periodo_mensual(request.args.get("mes", ""))
    personas = consultar_planilla(
        ps, escritura, inicio, fin, request.args.get("personal", "activos")
    )
    return jsonify(mes=inicio.strftime("%Y-%m"), dias=dias, registros=personas)
