"""Asignaciones de validación de Rendición, independientes del acceso de lectura."""
import json
import re
from flask import g
from models import AppConfig, Usuario, Proyecto, AccesoProyecto
from db import db

ADMIN_ROLES = ('zeno', 'suport', 'admin')
PROYECTOS = ('ENTEL', 'INTEGRATEL', 'CLARO')
CLAVE = 'rendicion_validadores_proyecto'


def configuracion():
    if not hasattr(g, '_rend_validadores'):
        proyecto = Proyecto.query.filter_by(nombre='Rendicion').first()
        cfg = AppConfig.query.filter_by(proyecto_id=proyecto.id, clave=CLAVE).first() if proyecto else None
        try:
            valor = json.loads(cfg.valor) if cfg else {}
        except (ValueError, TypeError):
            valor = {'activo': True, 'asignaciones': {}}
        if not isinstance(valor, dict) or not isinstance(valor.get('asignaciones', {}), dict):
            valor = {'activo': True, 'asignaciones': {}}
        g._rend_validadores = valor
    return g._rend_validadores


def proyecto_fila(row):
    texto = str(row.get('Nombre del proyecto') or row.get('NOMBRE DEL PROYECTO') or row.get('PROYECTO') or row.get('CLIENTE') or '').upper()
    encontrados = [p for p in PROYECTOS if re.search(r'\b' + p + r'\b', texto)]
    return encontrados[0] if len(encontrados) == 1 else ''


def puede_validar(row, usuario_id, rol):
    if str(rol).lower() in ADMIN_ROLES:
        return True
    cfg = configuracion()
    if not cfg.get('activo'):
        return True  # Compatibilidad hasta que el administrador configure la regla.
    return proyecto_fila(row) in cfg.get('asignaciones', {}).get(str(usuario_id), [])


def accesos_rendicion(usuarios):
    """{usuario_id: ¿lleva el módulo Rendición en su menú?} para toda la lista.

    Aplica la misma regla que `services.utilidades.puede_rendicion` para el
    módulo Rendición (zeno/suport ven todos los módulos; el resto, solo los que
    tiene asignados), pero resuelta con dos consultas fijas en vez de una por
    usuario: la pantalla de validadores lista a todos los usuarios.
    """
    proyecto = Proyecto.query.filter_by(nombre='Rendicion').first()
    if proyecto is None:
        return {u.id: False for u in usuarios}
    acceso = {u.id: str(u.rol or '').strip().lower() in ('zeno', 'suport') for u in usuarios}
    consultados = [uid for uid, tiene in acceso.items() if not tiene]
    if consultados:
        asignados = db.session.query(AccesoProyecto.usuario_id).filter(
            AccesoProyecto.usuario_id.in_(consultados),
            AccesoProyecto.proyecto_id == proyecto.id).all()
        for (usuario_id,) in asignados:
            acceso[usuario_id] = True
    return acceso


def guardar(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('activo'), bool) or not isinstance(payload.get('asignaciones'), dict):
        raise ValueError('Configuración inválida.')
    from services.usuarios import usuarios_activos
    usuarios = {str(u.id) for u in usuarios_activos()}
    asignaciones = {}
    for uid, proyectos in payload['asignaciones'].items():
        if uid not in usuarios or not isinstance(proyectos, list) or any(p not in PROYECTOS for p in proyectos):
            raise ValueError('Usuario o proyecto inválido.')
        asignaciones[uid] = sorted(set(proyectos))
    proyecto = Proyecto.query.filter_by(nombre='Rendicion').first()
    if not proyecto:
        raise ValueError('No existe el módulo Rendición.')
    cfg = AppConfig.query.filter_by(proyecto_id=proyecto.id, clave=CLAVE).first()
    if not cfg:
        cfg = AppConfig(proyecto_id=proyecto.id, clave=CLAVE)
        db.session.add(cfg)
    valor = {'activo': payload['activo'], 'asignaciones': asignaciones}
    cfg.valor = json.dumps(valor)
    db.session.commit()
    g._rend_validadores = valor
    return valor


def error_edicion(proyecto_id, row, cambios, rol):
    """La edición genérica no puede saltarse el flujo ni cambiar su ámbito."""
    proyecto = db.session.get(Proyecto, proyecto_id)
    if not proyecto or proyecto.nombre != 'Rendicion':
        return None
    if 'ESTADO' in cambios and str(cambios['ESTADO'] or '').strip().upper() != str(row.get('ESTADO') or 'PENDIENTE').strip().upper():
        return 'El estado se cambia únicamente con los botones del flujo.'
    if rol not in ADMIN_ROLES and configuracion().get('activo'):
        nuevo = {**row, **cambios}
        if proyecto_fila(nuevo) != proyecto_fila(row):
            return 'Solo administración puede cambiar el proyecto de una rendición.'
    return None
