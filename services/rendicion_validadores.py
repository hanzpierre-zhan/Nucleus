"""Protecciones de edición de Rendición; el acceso lo controla el ámbito de proyectos."""
import re
from models import Proyecto
from db import db

ADMIN_ROLES = ('zeno', 'suport', 'admin')
PROYECTOS = ('ENTEL', 'INTEGRATEL', 'CLARO')
CLAVE = 'rendicion_validadores_proyecto'  # Configuración histórica, ya no se aplica.


def proyecto_fila(row):
    texto = str(row.get('Nombre del proyecto') or row.get('NOMBRE DEL PROYECTO') or row.get('PROYECTO') or row.get('CLIENTE') or '').upper()
    encontrados = [p for p in PROYECTOS if re.search(r'\b' + p + r'\b', texto)]
    return encontrados[0] if len(encontrados) == 1 else ''


def error_edicion(proyecto_id, row, cambios, rol):
    """La edición genérica no puede saltarse el flujo ni cambiar su ámbito."""
    proyecto = db.session.get(Proyecto, proyecto_id)
    if not proyecto or proyecto.nombre != 'Rendicion':
        return None
    if 'ESTADO' in cambios and str(cambios['ESTADO'] or '').strip().upper() != str(row.get('ESTADO') or 'PENDIENTE').strip().upper():
        return 'El estado se cambia únicamente con los botones del flujo.'
    if rol not in ADMIN_ROLES:
        nuevo = {**row, **cambios}
        if proyecto_fila(nuevo) != proyecto_fila(row):
            return 'Solo administración puede cambiar el proyecto de una rendición.'
    return None
