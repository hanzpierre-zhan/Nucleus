"""Recupera únicamente configuración de columnas de Entel, una sola vez."""
import json
from datetime import datetime, timezone

VERSION = 'entel_columnas_restauradas_v1'
RESPALDO = VERSION + '_backup'
ORIGEN = 'flm_limpieza_backup_20261006_102327'
COLUMNAS = [
    'Número de WO', 'Autin TT', 'Hora de Creación del TT', 'Hora de Cierre del TT',
    'Estado del TT', 'Hora de Clear de la Alarma', 'Alarma', 'Causa raíz',
    'Tipo de Outage', 'Código Site', 'Nombre de Site', 'Prioridad del Site',
    'Tipo tarea', 'Antigüedad (días)', 'Antigüedad (hh:mm:ss)', 'Departamento',
    'Provincia', 'Distrito', 'Estado de la tarea (WO State)', 'O&M asignado',
    'Fecha de creación (WO Creation date)', 'Comentarios Suspend',
    'Comentarios complete', 'Comentarios adicionales', 'Category', 'Operate Phase',
    'Nombre de personal FLM asignado', 'Estado suspendido',
    'Fecha y hora de WO a estado complete', 'Fecha y hora de estado leave',
    'Fecha y hora de WO a estado close', 'Fecha y hora de cancelación de WO',
    'Es VIP', 'Fault Level', 'Number of DC Alarms',
]


def _lista(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, list):
        raise ValueError('Configuración de columnas de Entel inválida; no se reemplazó.')
    return result


def preparar(schema, layout, anterior):
    """Une columnas sin descartar las actuales y conserva orden y anchos."""
    schema = _lista(schema)
    layout = _lista(layout)
    respaldo = json.loads(anterior) if isinstance(anterior, str) else (anterior or {})
    historicas = _lista(respaldo.get('quitadas_schema', []))
    recuperar = list(dict.fromkeys(COLUMNAS + historicas))
    if any(not isinstance(c, str) or not c for c in recuperar):
        raise ValueError('El respaldo histórico contiene columnas inválidas.')
    new_schema = list(dict.fromkeys(schema + recuperar))
    originales = {c['field']: c for c in _lista(respaldo.get('column_layout', []))
                  if isinstance(c, dict) and c.get('field')}
    new_layout = [dict(c) for c in layout]
    por_campo = {c.get('field'): c for c in new_layout}
    for field in recuperar:
        if field not in por_campo:
            column = dict(originales.get(field, {'field': field}))
            new_layout.append(column)
            por_campo[field] = column
        por_campo[field]['visible'] = True
    if '_key' in por_campo:
        por_campo['_key']['visible'] = True
    return new_schema, new_layout


def instalar():
    from db import db
    from models import Proyecto, AppConfig
    proyecto = Proyecto.query.filter_by(nombre='FLM - ENTEL').with_for_update().first()
    if not proyecto:
        return False
    configs = {c.clave: c for c in AppConfig.query.filter_by(proyecto_id=proyecto.id)}
    if VERSION in configs:
        db.session.commit()
        return False
    schema = configs.get('app_schema')
    layout = configs.get('column_layout')
    if not schema:
        db.session.commit()
        return False
    anterior = configs[ORIGEN].valor if ORIGEN in configs else '{}'
    new_schema, new_layout = preparar(schema.valor, layout.valor if layout else '[]', anterior)
    copia = {'fecha':datetime.now(timezone.utc).isoformat(), 'app_schema':schema.valor,
             'column_layout':layout.valor if layout else None}
    if RESPALDO not in configs:
        db.session.add(AppConfig(proyecto_id=proyecto.id, clave=RESPALDO,
                                 valor=json.dumps(copia, ensure_ascii=False)))
    schema.valor = json.dumps(new_schema, ensure_ascii=False)
    if layout:
        layout.valor = json.dumps(new_layout, ensure_ascii=False)
    else:
        db.session.add(AppConfig(proyecto_id=proyecto.id, clave='column_layout',
                                 valor=json.dumps(new_layout, ensure_ascii=False)))
    db.session.add(AppConfig(proyecto_id=proyecto.id, clave=VERSION, valor='aplicado'))
    db.session.commit()
    return True
