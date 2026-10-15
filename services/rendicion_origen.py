"""Las solicitudes de Entel - Pext se reciben únicamente en Anton."""


def recibir_en_nucleus(datos):
    proyecto = str(datos.get('Nombre del proyecto') or '').strip().casefold()
    return proyecto != 'entel - pext'
