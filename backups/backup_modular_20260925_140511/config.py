# -*- coding: utf-8 -*-
"""Configuración por entorno (12-factor). Las claves se leen de variables de
entorno. DATABASE_URL se resuelve en tiempo de create_app() para permitir
override en tests y despliegues."""
import os
import re

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalizar_db_url(url):
    """Convierte postgres:// -> postgresql://, limpia channel_binding
    y asegura sslmode=require para conexiones cloud."""
    if not url:
        return url
    u = url.strip()
    if u.startswith('postgres://'):
        u = 'postgresql://' + u[len('postgres://'):]
    u = re.sub(r'[?&]channel_binding=[^&]*', '', u)
    if 'sslmode=' not in u:
        sep = '&' if '?' in u else '?'
        u = f'{u}{sep}sslmode=require'
    return u


class Config:
    """Configuración base — válida para todos los entornos."""
    TESTING = False
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'nucleus_dev_key_change_me')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    EVIDENCIA_DIR = os.path.join(BASE_DIR, 'static', 'evidencia')
    EVIDENCIA_MAX_LADO = int(os.environ.get('EVIDENCIA_MAX_LADO', 1280))
    EVIDENCIA_CALIDAD = int(os.environ.get('EVIDENCIA_CALIDAD', 80))
    # Backblaze B2
    B2_ENDPOINT_URL = os.environ.get('B2_ENDPOINT_URL', '')
    B2_KEY_ID = os.environ.get('B2_KEY_ID', '')
    B2_APP_KEY = os.environ.get('B2_APP_KEY', '')
    B2_BUCKET = os.environ.get('B2_BUCKET', '')
    B2_REGION = os.environ.get('B2_REGION', 'us-west-004')
    # OneDrive backup 1
    OD_CLIENT_ID = os.environ.get('OD_CLIENT_ID', '')
    OD_CLIENT_SECRET = os.environ.get('OD_CLIENT_SECRET', '')
    OD_REFRESH_TOKEN = os.environ.get('OD_REFRESH_TOKEN', '')
    OD_ENABLED = bool(OD_CLIENT_ID and OD_REFRESH_TOKEN)
    # OneDrive backup 2
    OD_CLIENT_ID_2 = os.environ.get('OD_CLIENT_ID_2', '')
    OD_CLIENT_SECRET_2 = os.environ.get('OD_CLIENT_SECRET_2', '')
    OD_REFRESH_TOKEN_2 = os.environ.get('OD_REFRESH_TOKEN_2', '')
    OD_ENABLED_2 = bool(OD_CLIENT_ID_2 and OD_REFRESH_TOKEN_2)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

    @classmethod
    def get_sqlalchemy_uri(cls):
        url = os.environ.get('DATABASE_URL', '').strip()
        if url:
            return _normalizar_db_url(url)
        return 'sqlite:///' + os.path.join(BASE_DIR, 'nucleus.db').replace('\\', '/')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SECRET_KEY = 'test-secret'


def get_default_config():
    env = os.environ.get('FLASK_ENV', '').strip().lower()
    return {'development': DevelopmentConfig,
            'testing': TestingConfig}.get(env, ProductionConfig)
