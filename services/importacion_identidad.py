"""Identificadores de los archivos FLM; nunca deducirlos del tipo de tarea."""
CLAVES = {'FLM - CLARO': 'Ticket Id', 'FLM - INTEGRATEL': 'Task Id'}


def validar_clave(df, proyecto, seleccionada=''):
    esperada = CLAVES.get(proyecto)
    if not esperada:
        return seleccionada
    if esperada not in df.columns:
        raise ValueError(f'El archivo de {proyecto} debe contener {esperada}. No se importó ningún registro.')
    if seleccionada and seleccionada != esperada:
        raise ValueError(f'La clave de {proyecto} debe ser {esperada}, no {seleccionada}.')
    valores = df[esperada].fillna('').astype(str).str.strip()
    if valores.eq('').any():
        raise ValueError(f'Hay registros sin {esperada}. Completa sus identificadores antes de importar.')
    if valores.duplicated().any():
        raise ValueError(f'Hay valores repetidos en {esperada}. No se agruparon ni sobrescribieron registros.')
    df[esperada] = valores
    return esperada
