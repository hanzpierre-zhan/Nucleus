"""Backup de los WO antiguos de FLM - ENTEL (antes de usar Ticket ID).

Sus filas viven en otro proyecto, pero las fotos siguen en la carpeta de FLM - ENTEL
(/api/evidencia/foto/<id de FLM - ENTEL>/...). Las cotizaciones aún los encuentran aquí.
"""
NOMBRE = 'Backup FLM ENTEL'
ENTEL = 'FLM - ENTEL'


def _ids():
    from models import Proyecto
    return dict(Proyecto.query.filter(Proyecto.nombre.in_((ENTEL, NOMBRE)))
                .with_entities(Proyecto.nombre, Proyecto.id).all())


def proyectos_de_fotos(pid):
    """Proyectos cuyas filas pueden usar fotos guardadas bajo pid."""
    ids = _ids()
    if pid == ids.get(ENTEL) and NOMBRE in ids:
        return {pid, ids[NOMBRE]}
    return {pid}


def carpeta_de_fotos(pid):
    """El backup muestra fotos de la carpeta de FLM - ENTEL."""
    ids = _ids()
    return ids.get(ENTEL, pid) if pid == ids.get(NOMBRE) else pid
