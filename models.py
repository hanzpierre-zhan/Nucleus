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
