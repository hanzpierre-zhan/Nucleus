"""Consultas de asistencia y catálogo; sin respuestas HTTP ni controladores."""

import calendar
import json
from datetime import datetime, date
from db import db
from flask import abort
from models import Proyecto, NucleusData, AsistenciaDiaria, AsistenciaCambio
from services import espacios

ESTADOS = {
    "PRESENTE": "Presente",
    "FALTA": "Falta",
    "PERMISO": "Permiso",
    "DESCANSO": "Descanso",
    "VACACIONES": "Vacaciones",
    "LICENCIA": "Licencia",
    "PENDIENTE": "Sin marcar",
}


def roster(permitidos):
    dataper = Proyecto.query.filter_by(nombre="Dataper").first()
    if not dataper:
        return {}
    nombres = {p.nombre: pid for pid, p in permitidos.items()}
    salida = {}
    for fila in NucleusData.query.filter_by(proyecto_id=dataper.id):
        try:
            d = json.loads(fila.data_json)
        except (ValueError, TypeError):
            continue
        if not isinstance(d, dict):
            continue
        pid = nombres.get(espacios.nombre_negocio(d.get("PROYECTO")))
        if pid is None:
            continue
        nombre = str(d.get("TECNICO") or d.get("NOMBRE COMPLETO") or "").strip()
        salida[fila.id, pid] = {
            "personal_id": fila.id,
            "proyecto_id": pid,
            "proyecto": permitidos[pid].nombre,
            "nombre": nombre or "Sin nombre en Personal",
            "documento": str(d.get("DOCUMENTO") or fila.key_value),
            "activo": str(d.get("ESTADO") or "").strip().upper() in ("", "ACTIVO"),
        }
    return salida


def datos_registro(r):
    return {
        "estado": r.estado,
        "observacion": r.observacion,
        "version": r.version,
        "actualizado_en": r.actualizado_en.isoformat() if r.actualizado_en else None,
    }


def periodo_mensual(valor):
    try:
        inicio = datetime.strptime(valor, "%Y-%m").date()
        dias = calendar.monthrange(inicio.year, inicio.month)[1]
        return (inicio, date(inicio.year, inicio.month, dias), dias)
    except (ValueError, TypeError):
        abort(400, "Mes inválido.")


def filtro_personal(valor):
    if valor not in ("activos", "cesados", "ambos"):
        abort(400, "Filtro de personal inválido.")
    return valor


def registros_periodo(proyectos, inicio, fin):
    return AsistenciaDiaria.query.filter(
        AsistenciaDiaria.proyecto_id.in_(proyectos),
        AsistenciaDiaria.fecha >= inicio,
        AsistenciaDiaria.fecha <= fin,
    )


def consultar_dia(ps, escritura, fecha):
    base = roster(ps)
    registros = AsistenciaDiaria.query.filter(
        AsistenciaDiaria.proyecto_id.in_(ps), AsistenciaDiaria.fecha == fecha
    ).all()
    guardados = {(r.personal_id, r.proyecto_id): r for r in registros}
    salida = []
    for clave, p in base.items():
        if not p["activo"] and clave not in guardados:
            continue
        r = guardados.get(clave)
        salida.append(
            {
                **p,
                **(
                    datos_registro(r)
                    if r
                    else {"estado": "PENDIENTE", "observacion": "", "version": 0}
                ),
                "editar": p["proyecto_id"] in escritura
                and (p["activo"] or r is not None),
            }
        )
    for clave, r in guardados.items():
        if clave in base:
            continue
        salida.append(
            {
                "personal_id": r.personal_id,
                "proyecto_id": r.proyecto_id,
                "proyecto": ps[r.proyecto_id].nombre,
                "nombre": r.nombre,
                "documento": r.documento,
                "activo": False,
                "editar": r.proyecto_id in escritura,
                **datos_registro(r),
            }
        )
    salida.sort(key=lambda f: (f["proyecto"], f["nombre"].casefold(), f["documento"]))
    return salida


def consultar_planilla(ps, escritura, inicio, fin, filtro):
    base = roster(ps)
    filtro = filtro_personal(filtro)
    salida = {
        k: {**p, "editar": p["proyecto_id"] in escritura, "marcas": {}}
        for k, p in base.items()
    }
    registros = registros_periodo(ps, inicio, fin).all()
    for r in registros:
        clave = (r.personal_id, r.proyecto_id)
        p = salida.setdefault(
            clave,
            {
                "personal_id": r.personal_id,
                "proyecto_id": r.proyecto_id,
                "proyecto": ps[r.proyecto_id].nombre,
                "nombre": r.nombre,
                "documento": r.documento,
                "activo": False,
                "editar": r.proyecto_id in escritura,
                "marcas": {},
            },
        )
        p["marcas"][str(r.fecha.day)] = datos_registro(r)
    personas = [
        p
        for p in salida.values()
        if filtro == "ambos" or p["activo"] == (filtro == "activos")
    ]
    return sorted(personas, key=lambda p: (p["proyecto"], p["nombre"].casefold()))


def resumir(filas, ps):
    resumen = {}
    for r in filas:
        clave = (r.personal_id, r.proyecto_id)
        item = resumen.setdefault(
            clave,
            {
                "personal_id": r.personal_id,
                "proyecto": ps[r.proyecto_id].nombre,
                "nombre": r.nombre,
                "documento": r.documento,
                "estados": {e: 0 for e in ESTADOS},
            },
        )
        item["estados"][r.estado] += 1
    return list(resumen.values())


def filtrar_registros(filas, ps, filtro):
    if filtro is not None:
        filtro_personal(filtro)
        base = roster(ps)
        if filtro != "ambos":
            filas = [
                r
                for r in filas
                if bool(
                    base.get((r.personal_id, r.proyecto_id), {}).get("activo", False)
                )
                == (filtro == "activos")
            ]
    return filas


class ConflictoVersion(Exception):
    """El cliente intenta guardar sobre una versión que ya cambió."""


def guardar_marcas(ps, escritura, fecha, cambios, usuario_id):
    base = roster(ps)
    pendientes = []
    vistos = set()
    for marca in cambios:
        if not isinstance(marca, dict):
            raise ValueError("Formato inválido.")
        clave = (int(marca["personal_id"]), int(marca["proyecto_id"]))
        if clave in vistos:
            raise ValueError("Una persona aparece dos veces en el envío.")
        vistos.add(clave)
        if clave[1] not in escritura:
            abort(403)
        estado = marca.get("estado")
        nota = marca.get("observacion", "")
        if estado not in ESTADOS or not isinstance(nota, str) or len(nota) > 500:
            raise ValueError("Revisa estado y observación (máximo 500 caracteres).")
        r = AsistenciaDiaria.query.filter_by(
            personal_id=clave[0], proyecto_id=clave[1], fecha=fecha
        ).first()
        if r is None and (clave not in base or not base[clave]["activo"]):
            abort(403)
        if int(marca.get("version", -1)) != (r.version if r else 0):
            raise ConflictoVersion(
                "Otro usuario cambió la asistencia. Actualiza antes de guardar."
            )
        pendientes.append((clave, estado, nota.strip(), r))
    for clave, estado, nota, r in pendientes:
        anterior = datos_registro(r) if r else {}
        if r and r.estado == estado and (r.observacion == nota):
            continue
        if r is None:
            p = base[clave]
            r = AsistenciaDiaria(
                personal_id=clave[0],
                proyecto_id=clave[1],
                fecha=fecha,
                nombre=p["nombre"],
                documento=p["documento"],
            )
            db.session.add(r)
        r.estado = estado
        r.observacion = nota
        r.actualizado_por = usuario_id
        r.actualizado_en = datetime.utcnow()
        db.session.flush()
        db.session.add(
            AsistenciaCambio(
                asistencia_id=r.id,
                usuario_id=usuario_id,
                anterior_json=json.dumps(anterior),
                nuevo_json=json.dumps(datos_registro(r)),
            )
        )
    db.session.commit()
    return len(pendientes)
