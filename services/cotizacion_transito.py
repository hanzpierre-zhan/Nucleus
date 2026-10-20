"""Entrega de una cotización a la bandeja Tránsito, sin duplicar solicitudes."""
import json
from db import db
from models import Proyecto, NucleusData


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
