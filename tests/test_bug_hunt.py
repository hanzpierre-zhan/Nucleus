# -*- coding: utf-8 -*-
"""Auditoría /bug-hunt de Nucleus.

Convención:
  · Los tests que documentan un COMPORTAMIENTO ACTUAL (dead code, valores,
    contratos) PASAN.
  · Los tests que verifican el comportamiento CORRECTO/SEGURO están marcados con
    [BUG] y se ESPERA que FALLEN: cada fallo es un hallazgo confirmado.
"""
import os
import json

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 1. Arranque / smoke
# ═══════════════════════════════════════════════════════════════════════════
def test_app_arranca_en_testing(app):
    assert app is not None
    assert app.config['TESTING'] is True


def test_login_get_200(client):
    r = client.get('/login')
    assert r.status_code == 200


def test_login_credenciales_ok_redirige(client):
    r = client.post('/login', data={'username': 'zeno', 'password': 'zeno123', 'legal_accept': '1'})
    if r.status_code == 200 and b'name="consent_step"' in r.data:
        r = client.post('/login', data={'consent_step': '1', 'legal_accept': '1'})
    assert r.status_code in (301, 302)


def test_login_credenciales_malas_no_redirige(client):
    r = client.post('/login', data={'username': 'zeno', 'password': 'mala', 'legal_accept': '1'})
    assert r.status_code == 200


def test_endpoint_protegido_redirige_a_login(client):
    r = client.get('/api/cotizacion/sustento')
    assert r.status_code in (301, 302)
    assert '/login' in r.headers.get('Location', '')


# ═══════════════════════════════════════════════════════════════════════════
# 2. [BUG] 404 devuelve JSON en vez de página HTML
# ═══════════════════════════════════════════════════════════════════════════
def test_bug_404_devuelve_pagina_no_json(client):
    """El handler global convierte TODO HTTPException en JSON, incluso la
    navegación HTML. Un usuario que teclea mal una URL no ve página amigable."""
    r = client.get('/esta-ruta-no-existe-jamas-123')
    assert r.status_code == 404
    assert 'text/html' in r.content_type, (
        'FALLO: 404 respondió %s en lugar de HTML' % r.content_type)


# ═══════════════════════════════════════════════════════════════════════════
# 3. [BUG] Fuga de detalle interno en errores 500 (info-leak)
# ═══════════════════════════════════════════════════════════════════════════
def test_bug_500_no_filtra_detalle_interno():
    """app.py:36-40 devuelve str(e) al cliente: rutas internas, SQL o secretos
    pueden quedar expuestos. Se registra una ruta temporal que revienta."""
    from app import create_app
    from config import TestingConfig
    import tempfile

    class Cfg(TestingConfig):
        EVIDENCIA_DIR = os.path.join(tempfile.mkdtemp(prefix='nucleus_leak_'), 'ev')

    a = create_app(Cfg)
    detalle = 'DETALLE-INTERNO-SECRETO-12345'

    @a.route('/__boom_bughunt')
    def _boom():
        raise RuntimeError(detalle)

    c = a.test_client()
    r = c.get('/__boom_bughunt')
    assert r.status_code == 500
    body = r.get_data(as_text=True)
    assert detalle not in body, (
        'FALLO: el detalle interno de la excepción se filtró al cliente: %r' % body)


# ═══════════════════════════════════════════════════════════════════════════
# 4. [BUG] Bypass de open-redirect con URL protocol-relative (//dominio)
# ═══════════════════════════════════════════════════════════════════════════
def test_bug_open_redirect_protocol_relative(auth_client):
    """auth.py:192-197 solo bloquea si urlparse trae scheme http/https. Una URL
    '//evil.com' pasa el filtro y el navegador redirige al dominio externo."""
    r = auth_client.get('/switch_project/1?next=//evil.com')
    loc = r.headers.get('Location', '')
    assert not loc.startswith('//'), (
        'FALLO: open redirect vía protocol-relative. Location=%r' % loc)


def test_open_redirect_http_externo_si_bloqueado(auth_client):
    """Contraste: el formato con scheme sí se neutraliza."""
    r = auth_client.get('/switch_project/1?next=http://evil.com')
    loc = r.headers.get('Location', '')
    assert 'evil.com' not in loc


# ═══════════════════════════════════════════════════════════════════════════
# 5. Código muerto: el "hermano FLM" siempre es None
# ═══════════════════════════════════════════════════════════════════════════
def test_flm_hermano_id_siempre_none():
    import services
    for pid in (1, 5, 10, 11, 12, 13, 999):
        assert services._flm_hermano_id(pid) is None


def test_flm_pair_ids_segundo_siempre_none(app):
    import services
    with app.app_context():
        _, her = services._flm_pair_ids()
        assert her is None


# ═══════════════════════════════════════════════════════════════════════════
# 6. Contrato de tamaño: MAX_CONTENT_LENGTH vs mensaje del handler 413
# ═══════════════════════════════════════════════════════════════════════════
def test_max_content_length_es_100mb(app):
    assert app.config['MAX_CONTENT_LENGTH'] == 100 * 1024 * 1024


# ═══════════════════════════════════════════════════════════════════════════
# 7. Helpers de Combustible (lógica pura)
# ═══════════════════════════════════════════════════════════════════════════
def test_combustible_fecha_norm_y_ord():
    import services
    assert services._combustible_fecha_norm('2026-01-02') == '2026-01-02 00:00'
    assert services._combustible_fecha_norm('2/1/2026 8:5') == '2026-01-02 08:05'
    # fin de día para ordenar (00:00 -> 23:59)
    assert services._combustible_fecha_ord('2026-01-02') == '2026-01-02 23:59'


def test_parse_galones():
    import services
    assert services._parse_galones('12,5') == 12.5
    assert services._parse_galones('') == 0.0
    assert services._parse_galones('abc') == 0.0


def test_combustible_chequear_saldo_negativo():
    import services
    filas = [{'key': 'a', 'fecha': '2026-01-01 00:00', 'mov': 'GASTO', 'gal': 10.0}]
    ok, info = services._combustible_chequear(filas)
    assert ok is False
    filas2 = [{'key': 'a', 'fecha': '2026-01-01 00:00', 'mov': 'INGRESO', 'gal': 10.0},
              {'key': 'b', 'fecha': '2026-01-02 00:00', 'mov': 'GASTO', 'gal': 4.0}]
    ok2, info2 = services._combustible_chequear(filas2)
    assert ok2 is True
    assert info2['saldo_final'] == 6.0


# ═══════════════════════════════════════════════════════════════════════════
# 8. Sustento / evidencia: validación de entrada
# ═══════════════════════════════════════════════════════════════════════════
def test_sustento_sin_key_devuelve_400(auth_client):
    r = auth_client.get('/api/cotizacion/sustento')
    assert r.status_code == 400
    assert 'clave' in r.get_data(as_text=True).lower()


def test_evidencia_indice_no_numerico_devuelve_400(auth_client):
    r = auth_client.post('/api/evidencia/subir', data={'indice': 'abc'})
    assert r.status_code == 400


def test_cambio_password_nueva_corta_400(client):
    r = client.post('/api/auth/cambiar-password', json={
        'username': 'zeno', 'actual': 'zeno123', 'nueva': 'abc'})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 9. Opciones de engine: connect_args solo aplica a Postgres
# ═══════════════════════════════════════════════════════════════════════════
def test_sqlite_no_tiene_connect_args():
    from app import create_app
    from config import TestingConfig
    import tempfile

    class Cfg(TestingConfig):
        # hereda SQLALCHEMY_ENGINE_OPTIONS con connect_args (Postgres)
        EVIDENCIA_DIR = os.path.join(tempfile.mkdtemp(prefix='nucleus_eng_'), 'ev')

    a = create_app(Cfg)
    assert 'connect_args' not in (a.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})


# ═══════════════════════════════════════════════════════════════════════════
# 10. Compresión gzip
# ═══════════════════════════════════════════════════════════════════════════
def test_gzip_disponible(client):
    r = client.get('/login', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
