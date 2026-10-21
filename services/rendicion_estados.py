"""Lectura canónica del estado de rendición, compartida con Analytics."""


def estado_de(d):
    return str(d.get("ESTADO", "") or "").strip().upper() or "PENDIENTE"


def etapa_de(row):
    estado = estado_de(row)
    subestado = str(row.get('SUBESTADO') or '').strip().upper()
    if subestado == 'ARCHIVADO' and estado == 'SUSTENTADO':
        return 'ARCHIVADO'
    if subestado == 'OBSERVADO' and estado in ('CON SUSTENTO', 'SUSTENTADO'):
        return 'OBSERVADO'
    if estado == "RECHAZADO":
        destino = row.get("_RECHAZO_ETAPA")
        if destino in ("VALIDACION", "EVIDENCIA"):
            return destino
        # Mostrar los rechazos históricos sin borrar ni reescribir registros.
        return {
            "VALIDADO": "VALIDACION",
            "DEPOSITADO": "EVIDENCIA",
            "CON SUSTENTO": "EVIDENCIA",
            "OBSERVADO": "EVIDENCIA",
            "SUSTENTADO": "EVIDENCIA",
        }.get(str(row.get("RECHAZADO DESDE") or "").strip().upper(), "ANULADO")
    return {
        "TRANSITO": "TRANSITO",
        "PENDIENTE": "VALIDACION",
        "VALIDADO": "DEPOSITOS",
        "DEPOSITADO": "EVIDENCIA",
        "CON SUSTENTO": "SUSTENTO",
        "OBSERVADO": "OBSERVADO",
        "SUSTENTADO": "ATENDIDO",
        "ARCHIVADO": "ARCHIVADO",
        "ANULADO": "ANULADO",
    }.get(estado, "VALIDACION")
