# -*- coding: utf-8 -*-
"""Modelos de base de datos de Nucleus.
Importa db desde db.py para desacoplar el singleton de la factory."""
from datetime import datetime
from db import db


class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), default='')
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), default='supervisor')


class ConformidadUsuario(db.Model):
    __tablename__ = 'conformidad_usuario'
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), primary_key=True)
    version = db.Column(db.String(30), nullable=False)
    aceptado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Proyecto(db.Model):
    __tablename__ = 'proyectos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.String(200))
    icono = db.Column(db.String(50), default='fa-folder-open', nullable=False)


class AppConfig(db.Model):
    __tablename__ = 'app_config'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    clave = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('proyecto_id', 'clave', name='_proj_clave_uc'),)


class TokenStore(db.Model):
    """Almacén global clave/valor (p. ej. refresh token de OneDrive)."""
    __tablename__ = 'token_store'
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(50), unique=True, nullable=False)
    valor = db.Column(db.Text, nullable=False)


class NucleusData(db.Model):
    __tablename__ = 'nucleus_data'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    data_json = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('proyecto_id', 'key_value', name='_proj_key_uc'),)


class RendicionCorreo(db.Model):
    """Copia durable del correo, fuera del JSON que alimenta las tablas."""
    __tablename__ = 'rendicion_correos'
    id = db.Column(db.Integer, primary_key=True)
    origen_id = db.Column(db.Integer, db.ForeignKey('nucleus_data.id', ondelete='CASCADE'), nullable=False, index=True)
    nombre = db.Column(db.String(80), nullable=False)
    nombre_original = db.Column(db.String(255), nullable=False)
    contenido = db.deferred(db.Column(db.LargeBinary, nullable=False))
    __table_args__ = (db.UniqueConstraint('origen_id', 'nombre', name='_rend_correo_origen_nombre_uc'),)


class NucleusHistory(db.Model):
    __tablename__ = 'nucleus_history'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    data_json = db.Column(db.Text, nullable=False)
    fecha_consolidado = db.Column(db.DateTime, default=datetime.utcnow)


class FiltroMaestro(db.Model):
    __tablename__ = 'filtros_maestros'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    columna = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.UniqueConstraint('proyecto_id', 'columna', 'valor', name='_proj_filtro_uc'),)


class TablaMaestra(db.Model):
    __tablename__ = 'tablas_maestras'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    columna_criterio = db.Column(db.String(100), nullable=False)
    valor_criterio = db.Column(db.String(100), nullable=False)
    nueva_columna = db.Column(db.String(100), nullable=False)
    nuevo_valor = db.Column(db.String(100), nullable=False)


class ReglaEstadoManual(db.Model):
    __tablename__ = 'reglas_estado_manual'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    columna_criterio = db.Column(db.String(100), nullable=False)
    valor_criterio = db.Column(db.String(100), nullable=False)
    columna_manual = db.Column(db.String(100), nullable=False)
    nuevo_valor = db.Column(db.String(100), nullable=False)


class AccesoProyecto(db.Model):
    __tablename__ = 'accesos_proyecto'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    restricciones = db.Column(db.Text, default='{}')
    __table_args__ = (db.UniqueConstraint('usuario_id', 'proyecto_id', name='_user_proj_uc'),)


class KpiConfig(db.Model):
    __tablename__ = 'kpi_configs'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    col_inicio = db.Column(db.String(100), nullable=False)
    restar_contra = db.Column(db.String(20), default='HOY')
    col_fin = db.Column(db.String(100), nullable=True)
    tipo = db.Column(db.String(20), default='DILACION')


class HistorialCambios(db.Model):
    __tablename__ = 'historial_cambios'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    username = db.Column(db.String(50), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    campo_modificado = db.Column(db.String(100), nullable=False)
    valor_anterior = db.Column(db.Text, nullable=True)
    valor_nuevo = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)


class Tecnico(db.Model):
    __tablename__ = 'tecnicos'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    contrata = db.Column(db.String(120), default='')
    especialidad = db.Column(db.String(120), default='')
    telefono = db.Column(db.String(30), default='')


class Cotizacion(db.Model):
    __tablename__ = 'cotizaciones'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    key_value = db.Column(db.String(100), nullable=False, index=True)
    numero = db.Column(db.String(50), nullable=False)
    nota = db.Column(db.Text, default='')
    cotizado_por = db.Column(db.String(100), default='')
    revisado_por = db.Column(db.String(100), default='')
    gastos_json = db.Column(db.Text, default='[]')
    mano_obra_json = db.Column(db.Text, default='[]')
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)
    bloqueada = db.Column(db.Boolean, default=True)
    formato = db.Column(db.String(20), default='')
    site = db.Column(db.String(200), default='')
    supervisor = db.Column(db.String(120), default='')
    items_json = db.Column(db.Text, default='[]')


class Notificacion(db.Model):
    """Avisos del flujo de Rendicion (quién validó, depositó, rechazó...).

    Los ve todo usuario que tenga el módulo Rendicion asignado.
    """
    __tablename__ = 'notificaciones'
    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, index=True)
    tipo = db.Column(db.String(20), default='')      # validar/depositar/rechazar/sustentar/revertir
    texto = db.Column(db.Text, default='')
    color = db.Column(db.String(20), default='#007AFF')
    autor = db.Column(db.String(80), default='')     # usuario que hizo clic
    creada_en = db.Column(db.String(19), default='')
    leida_por = db.Column(db.Text, default='')       # ids de usuario, separados por coma


class RefacturableDetalle(db.Model):
    """Seguimiento independiente de una cotización aprobada, sin duplicarla."""
    __tablename__ = 'refacturable_detalle'
    origen_id = db.Column(db.Integer, db.ForeignKey('nucleus_data.id'), primary_key=True)
    data_json = db.Column(db.Text, nullable=False, default='{}')
    actualizado_por = db.Column(db.String(100), default='')
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow)


class LiquidacionNumero(db.Model):
    """Numeración permanente; no depende del orden ni del filtro de la tabla."""
    __tablename__ = 'liquidacion_numero'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    origen_id = db.Column(db.Integer, nullable=False, unique=True)
    __table_args__ = {'sqlite_autoincrement': True}


class PerfilEspacio(db.Model):
    __tablename__ = 'espacio_perfiles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False, unique=True)
    permisos_json = db.Column(db.Text, nullable=False, default='{}')


class ProyectoNegocio(db.Model):
    """Registro extensible de espacios; su operación sigue en Proyecto."""
    __tablename__ = 'espacio_proyectos'
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), primary_key=True)
    nombre = db.Column(db.String(80), nullable=False, unique=True)


class CuentaEspacio(db.Model):
    """Mantiene el aislamiento aunque se revoque la última asignación."""
    __tablename__ = 'espacio_cuentas'
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), primary_key=True)


class AccesoEspacio(db.Model):
    __tablename__ = 'espacio_accesos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)
    perfil_id = db.Column(db.Integer, db.ForeignKey('espacio_perfiles.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('usuario_id', 'proyecto_id', name='uq_espacio_usuario_proyecto'),)


class ClasificacionEspacio(db.Model):
    """Asignación revisada sin mover ni duplicar el registro original."""
    __tablename__ = 'espacio_clasificaciones'
    registro_id = db.Column(db.Integer, db.ForeignKey('nucleus_data.id'), primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False)


class AuditoriaEspacio(db.Model):
    __tablename__ = 'espacio_auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    accion = db.Column(db.String(80), nullable=False)
    detalle_json = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AsistenciaDiaria(db.Model):
    """Marcación explícita; ausencia de registro significa pendiente, nunca falta."""
    __tablename__ = 'asistencia_diaria'
    id = db.Column(db.Integer, primary_key=True)
    personal_id = db.Column(db.Integer, db.ForeignKey('nucleus_data.id'), nullable=False, index=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    estado = db.Column(db.String(24), nullable=False)
    observacion = db.Column(db.String(500), nullable=False, default='')
    nombre = db.Column(db.String(200), nullable=False)
    documento = db.Column(db.String(100), nullable=False)
    actualizado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (db.UniqueConstraint('personal_id','proyecto_id','fecha',name='uq_asistencia_persona_proyecto_dia'),)


class AsistenciaCambio(db.Model):
    __tablename__ = 'asistencia_cambios'
    id = db.Column(db.Integer, primary_key=True)
    asistencia_id = db.Column(db.Integer, db.ForeignKey('asistencia_diaria.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    anterior_json = db.Column(db.Text, nullable=False, default='{}')
    nuevo_json = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ConciliacionOrigen(db.Model):
    __tablename__ = 'conciliacion_origen'
    id = db.Column(db.Integer, primary_key=True)
    fuente_sha256 = db.Column(db.String(64), nullable=False)
    fuente = db.Column(db.String(160), nullable=False)
    origen_id = db.Column(db.String(80), nullable=False)
    destino_id = db.Column(db.Integer, db.ForeignKey('nucleus_data.id'), nullable=False)
    original_json = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('fuente_sha256','origen_id',name='uq_conciliacion_origen'),)


class LpuRegistro(db.Model):
    __tablename__ = 'lpu_catalogo'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), nullable=False, unique=True)
    unit = db.Column(db.String(100), nullable=False, default='')
    description_es = db.Column(db.Text, nullable=False, default='')
    description_en = db.Column(db.Text, nullable=False, default='')
    activity = db.Column(db.Text, nullable=False, default='')
    actualizado_por = db.Column(db.String(100), nullable=False, default='')
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
