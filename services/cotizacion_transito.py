"""Entrega de una cotización a la bandeja Tránsito, sin duplicar solicitudes."""
import json
from db import db
from models import Proyecto, NucleusData


def indice_transito():
    """Bandeja derivada del vínculo existente; no mueve ni duplica expedientes."""
    destino = Proyecto.query.filter_by(nombre='Rendicion').first()
    resultado = {}
    if destino:
        for fila in NucleusData.query.filter_by(proyecto_id=destino.id).yield_per(500):
            datos = json.loads(fila.data_json or '{}')
            origen = datos.get('_COTIZACION_ORIGEN') or {}
            if str(datos.get('ESTADO', '')).strip().upper() == 'TRANSITO' and origen.get('id'):
                resultado[origen['key']] = {'key': fila.key_value, 'fecha': datos.get('FECHA ENVIO TRANSITO', ''),
                                           'usuario': datos.get('ENVIADO A TRANSITO POR', '')}
    return resultado


def enviar(fuente, datos, usuario, fecha):
    db.session.query(NucleusData.id).filter_by(id=fuente.id).with_for_update().one()
    destino = Proyecto.query.filter_by(nombre='Rendicion').first()
    if destino is None:
        raise ValueError('No existe el módulo Rendición.')
    clave = 'COT-' + str(fuente.id)
    fila = NucleusData.query.filter_by(proyecto_id=destino.id, key_value=clave).first()
    if fila is None:
        solicitud = {
            'ESTADO': 'TRANSITO', 'Marca temporal': fecha,
            'N° COTIZACION': fuente.key_value,
            'Nombre del proyecto': datos.get('CLIENTE') or datos.get('PROYECTO') or '',
            'Nombre de site': datos.get('NOMBRE SITE') or '',
            'Motivo de la solicitud': datos.get('MOTIVO') or '',
            'Monto total del depósito': datos.get('SUB TOTAL + FEE', ''),
            'NUMERO WO': datos.get('NUMERO WO') or '',
            'TIPO DE PRESUPUESTO': datos.get('TIPO DE GASTO') or '',
            'ENVIADO A TRANSITO POR': usuario, 'FECHA ENVIO TRANSITO': fecha,
            '_COTIZACION_ORIGEN': {'id': fuente.id, 'proyecto_id': fuente.proyecto_id,
                                   'key': fuente.key_value},
        }
        fila = NucleusData(proyecto_id=destino.id, key_value=clave,
                           data_json=json.dumps(solicitud, ensure_ascii=False))
        db.session.add(fila)
    # Se guarda en la misma transacción que el cambio a Caja chica.
    # Repetir el envío nunca reinicia el estado de una rendición ya existente.
    datos['_RENDICION_TRANSITO'] = {'proyecto_id': destino.id, 'key': clave}
    return fila


def monto_transito(valor):
    """Monto a depositar por Tránsito ('1234.50'), o None si no es un número mayor a 0."""
    from decimal import Decimal, InvalidOperation
    try:
        monto = Decimal(str(valor or '').replace(',', '').strip()).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None
    return str(monto) if monto.is_finite() and monto > 0 else None


def provision(monto):
    """Provisión para pasar a proveedor: lo depositado por Tránsito + 20 %."""
    from decimal import Decimal
    return str((Decimal(monto) * Decimal('1.20')).quantize(Decimal('0.01')))
