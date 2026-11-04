"""Registros excluidos de las importaciones FLM, según su estado de origen."""
ESTADOS = {
    'FLM - CLARO': ('Task Status', 'Estado de la tarea (WO State)'),
    'FLM - INTEGRATEL': ('Task Status', 'Estado de la tarea (WO State)'),
    'FLM - ENTEL': ('Estado de la tarea (WO State)', 'Task Status'),
    'FLM - PEXT': ('Estado de la tarea', 'Estado de la tarea (WO State)', 'Task Status'),
    'PEXT': ('Estado de la tarea', 'Estado de la tarea (WO State)', 'Task Status'),
}


def cancelado(datos, proyecto):
    campos = {str(k).strip().casefold(): v for k, v in datos.items()}
    for nombre in ESTADOS.get(str(proyecto).strip().upper(), ()):
        valor = str(campos.get(nombre.casefold()) or '').strip()
        if valor:
            return valor.casefold() == 'canceled'
    return False
