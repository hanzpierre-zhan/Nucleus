"""Categorías de gasto del formulario; no confundirlas con presupuesto."""
import re
import unicodedata

OPCIONES = ('PEAJE', 'COMPRAS', 'ALQUILER', 'PASAJE', 'VIATICOS', 'HOSPEDAJE', 'COCHERA', 'MATERIAL', 'ACARREO', 'OTROS')
CAMPO = 'Tipo de gasto'
META = '_TIPO_GASTO_HOMOLOGACION'
META_AMPLIACION = '_TIPO_GASTO_AMPLIACION'


def ampliar_otros(datos):
    """Reclasifica OTROS solo con evidencia explícita del concepto solicitado.

    No interpreta nombres, sitios, importes ni el presupuesto como categorías.
    Conserva el resto de selecciones y el historial de homologación anterior.
    """
    salida = dict(datos)
    if (datos.get(META_AMPLIACION) or {}).get('homologado') == datos.get(CAMPO):
        return salida
    partes = [p.strip() for p in str(datos.get(CAMPO) or '').split(',')]
    if 'OTROS' not in partes or not valido(datos.get(CAMPO)):
        return salida
    motivo = texto(datos.get('Motivo de la solicitud'))
    previo = datos.get(META) or {}
    detalle = texto(previo.get('original', ''))
    # El motivo prevalece; el detalle original sirve cuando el motivo es genérico.
    contexto = motivo + ' ' + detalle
    nuevas = set()
    if re.search(r'\b(ACARREO\w*|ACARREAR|ACARREPO|CARREO)\b|\bCARGA Y DESCARGA\b', contexto):
        nuevas.add('ACARREO')
    # Envío/alquiler de material es un servicio, no adquisición de material.
    material = bool(re.search(r'\b(MATERIALES?|CONSUMIBLES?|REPUESTOS?|EPPS?|FUSIBLES?|CABLES?|TARJETA CONTROLADORA|LIMPIA CARBURADOR)\b', contexto))
    servicio = bool(re.search(r'\b(ENVIO|RECOJO|TRANSPORTE|TRASLADO|ENCOMIENDA|ALQUILER|REPARACION)\b', motivo))
    compra = bool(re.search(r'\b(COMPRAS?|ADQUISICION|SUMINISTRO)\b', motivo))
    if material and (compra or (not servicio and re.search(r'\b(MATERIALES?|CONSUMIBLES?)\b', motivo))):
        nuevas.add('MATERIAL')
    if not nuevas:
        return salida
    otras = bool(re.search(r'\b(CUSTODIOS?|FERIADO|BONO|REPARACION|LIMPIEZA|MONTAJE|DESMONTAJE|ENCENDIDO|MONITOREO|APAGADO)\b', motivo))
    categorias = set(partes) - {'OTROS'} | nuevas
    # Categorías adicionales explícitas en solicitudes mixtas.
    categorias |= _inferir(motivo) - {'OTROS', 'COMPRAS'}
    if otras:
        categorias.add('OTROS')
    salida[CAMPO] = ', '.join(c for c in OPCIONES if c in categorias)
    salida[META_AMPLIACION] = {'anterior': datos[CAMPO], 'homologado': salida[CAMPO],
        'criterio': 'Concepto explícito del motivo y detalle original; sin inferir por identidad',
        'lote': 'gastos-material-acarreo-20261101'}
    return salida


def texto(valor):
    return ' '.join(unicodedata.normalize('NFKD', str(valor or '')).encode('ascii', 'ignore').decode().upper().split())


def valido(valor):
    partes = str(valor or '').split(',')
    return bool(partes) and all(p.strip() in OPCIONES for p in partes)


def validar_manual(valor):
    if not valido(valor):
        raise ValueError('Selecciona una o varias categorías válidas: ' + ', '.join(OPCIONES) + '.')
    return valor


def _inferir(valor):
    t = texto(valor)
    categorias = set()
    if re.search(r'\b(COCHERA|ESTACIONAMIENTO|PARQUEO|PARKING)\b', t): categorias.add('COCHERA')
    if re.search(r'\b(HOSPEDAJE|HOTEL|HOSTAL|PERNOCTE|PERNOCTAR)\b', t): categorias.add('HOSPEDAJE')
    if re.search(r'\b(VIATICOS?|DESAYUNOS?|ALMUERZOS?|CENAS?|ALIMENTOS?|ALIMENTACION|MERIENDA|REFRIGERIOS?)\b', t): categorias.add('VIATICOS')
    if re.search(r'\bPEAJES?\b', t): categorias.add('PEAJE')
    if re.search(r'\b(PASAJES?|PASAGES?|BOLETOS?|TAXI|MOTOTAXI)\b|\b(?:TRASLADO|TRANSPORTE)S? DE PERSONAL\b', t): categorias.add('PASAJE')
    if re.search(r'\b(ALQUILER|ALQUILERES|ALQUILAR|ALQUILA|ARRENDAMIENTO|ALQI)\b', t) and 'COCHERA' not in categorias: categorias.add('ALQUILER')
    if re.search(r'\b(COMPRAS?|COMPRAR|COMPRO|ADQUISICION|ADQUIRIR|SUMINISTRO|SUMINSTRO)\b', t): categorias.add('COMPRAS')
    if re.search(r'\b(CUSTODIO|CUSTODIAR|APOYOS?|CUADRILLAS?|INGENIERO|ING|ESPECIALISTA|FERIADO|REPARACION|CURSO|INSCRIPCION|COLEGIATURA|MANIOBRAS?|ACARREO|ACARREOS|ACARREPO|CARREO|FLETE|ENCOMIENDA|ENVIO|BANDEO|FLUVIAL|ALMACENAJE)\b|\bCARGA Y DESCARGA\b', t): categorias.add('OTROS')
    if t == 'OTROS': categorias.add('OTROS')
    if not categorias and re.search(r'\b(FUSIBLES?|CONSUMIBLES|CABLE|GALONERA)\b', t): categorias.add('COMPRAS')
    return categorias


def clasificar(datos):
    """Devuelve una copia, dejando las celdas válidas byte por byte intactas."""
    if CAMPO not in datos or valido(datos[CAMPO]):
        return dict(datos)
    original = str(datos.get(CAMPO) or '')
    seleccionadas = set()
    motivos = []
    ambiguo = False
    for fragmento in re.split(r'[,;\n]+', original):
        if not fragmento.strip(): continue
        t = texto(fragmento)
        if t in OPCIONES:
            seleccionadas.add(t)
        else:
            categorias = _inferir(fragmento)
            seleccionadas.update(categorias)
    # Contexto para los textos genéricos; no inferir por nombre del técnico/site
    # ni por el tipo de presupuesto (Gasto Cobra/Refacturable).
    contexto = ' '.join(str(datos.get(k) or '') for k in (
        'Motivo de la solicitud', 'Observaciones (Form)', 'COMENTARIOS SUSTENTO', 'OBSERVACIONES'))
    contexto_solicitud = ' '.join(str(datos.get(k) or '') for k in ('Motivo de la solicitud', 'Observaciones (Form)'))
    if re.match(r'^OTROS\s*[-:]', texto(original)):
        seleccionadas = {'OTROS'}
        motivos.append('Se conserva OTROS expresamente seleccionado; el detalle queda en el original')
    elif texto(original).startswith('ALMACENAJE') and 'ALQUILER' in _inferir(contexto_solicitud):
        seleccionadas = {'ALQUILER'}
        motivos.append('El motivo especifica alquiler de almacenaje')
    elif seleccionadas == {'OTROS'} and _inferir(contexto_solicitud) - {'OTROS'}:
        ambiguo = True
        motivos.append('Descripción y motivo sugieren conceptos distintos; conservar detalle para revisión')
    if not seleccionadas:
        seleccionadas = _inferir(contexto)
        motivos.append('Contexto del registro')
    else:
        motivos.append('Opciones originales y descripción de la celda')
    if not seleccionadas:
        seleccionadas = {'OTROS'}
        ambiguo = True
        motivos.append('Sin evidencia suficiente para una categoría específica')
    resultado = ', '.join(c for c in OPCIONES if c in seleccionadas)
    salida = dict(datos)
    previo = datos.get(META) or {}
    salida[CAMPO] = resultado
    salida[META] = {'original': previo.get('original', original), 'homologado': resultado,
                    'criterio': '; '.join(motivos), 'requiere_revision': ambiguo,
                    'lote': 'gastos-20261029'}
    return salida
