# -*- coding: utf-8 -*-
"""Rendición: rechazo desde Atendido, columna del motivo y URLs de foto.

Cubre los tres arreglos:
  · rechazar una solicitud en Atendido (SUSTENTADO) la devuelve a Evidencia;
  · el motivo queda en una columna propia (MOTIVO RECHAZO) y no solo dentro de
    OBSERVACIONES, que no es una columna del módulo;
  · las URLs de foto ya no llevan la llave cruda (la fecha con '/' y espacios),
    que el navegador cortaba al abrirla.
"""
import json
import pytest

from db import db
from models import Proyecto, NucleusData, AppConfig
from blueprints.rendicion import _claves_foto, _etapa_de


def _rend_proyecto():
    return Proyecto.query.filter_by(nombre='Rendicion').one()


def _crear(app, key, datos):
    with app.app_context():
        pid = _rend_proyecto().id
        db.session.add(NucleusData(proyecto_id=pid, key_value=key,
                                   data_json=json.dumps(datos, ensure_ascii=False)))
        db.session.commit()
        return pid


def _borrar(app, pid, key):
    with app.app_context():
        NucleusData.query.filter_by(proyecto_id=pid, key_value=key).delete()
        db.session.commit()


# ── Rechazo desde Atendido ────────────────────────────────────────────────────
def test_rechazar_desde_atendido_vuelve_a_evidencia(app, auth_client):
    key = 'REND-ATENDIDO-TEST'
    pid = _crear(app, key, {'ESTADO': 'SUSTENTADO', 'Monto total del depósito': '50'})
    try:
        r = auth_client.post('/api/rendicion/accion',
                             json={'key': key, 'accion': 'rechazar',
                                   'observaciones': 'Comprobante ilegible'})
        assert r.status_code == 200, r.data
        datos = r.json['newData']
        assert datos['ESTADO'] == 'RECHAZADO'
        assert datos['MOTIVO RECHAZO'] == 'Comprobante ilegible'
        assert datos['RECHAZADO DESDE'] == 'SUSTENTADO'
        # La etapa de un RECHAZADO manda a la hoja de Evidencia
        assert _etapa_de(datos) == 'EVIDENCIA'
    finally:
        _borrar(app, pid, key)


def test_rechazar_exige_motivo(app, auth_client):
    key = 'REND-SIN-MOTIVO-TEST'
    pid = _crear(app, key, {'ESTADO': 'SUSTENTADO'})
    try:
        r = auth_client.post('/api/rendicion/accion',
                             json={'key': key, 'accion': 'rechazar', 'observaciones': '  '})
        assert r.status_code == 400
    finally:
        _borrar(app, pid, key)


# ── URLs de foto ──────────────────────────────────────────────────────────────
def test_claves_foto_prueba_cruda_y_saneada():
    claves = _claves_foto('6/10/2026 14:30:00')
    assert '6/10/2026 14:30:00' in claves
    assert any(' ' not in c and '/' not in c for c in claves), claves


def test_url_de_foto_sin_llave_cruda(app):
    """La URL de una foto no debe llevar la llave cruda (fecha con '/' y espacios):
    el navegador la cortaba al abrirla y el archivo daba 'No encontrado'."""
    from werkzeug.utils import secure_filename
    with app.app_context():
        pid = _rend_proyecto().id
    clave_url = secure_filename('6/10/2026 14:30:00')
    url = '/api/rendicion/foto/%d/%s/%s?v=9' % (pid, clave_url, 'rendicion_pago.jpg')
    assert ' ' not in url, url
    # partes: '', 'api', 'rendicion', 'foto', '<pid>', '<llave>', '<nombre>?v=9'
    llave_en_url = url.split('/')[5]
    assert '/' not in llave_en_url and ' ' not in llave_en_url
    # y el servidor la resuelve igual con la llave cruda o con la saneada
    assert set(_claves_foto(clave_url)) == {clave_url}
    assert len(_claves_foto('6/10/2026 14:30:00')) == 2


# ── Migración: columna + backfill + URLs ─────────────────────────────────────
def test_migracion_rendicion_columna_backfill_y_urls(app):
    key = 'REND-MIGRA-TEST'
    with app.app_context():
        pid = _rend_proyecto().id
    _crear(app, key, {
        'ESTADO': 'RECHAZADO',
        'OBSERVACIONES': 'Falta el comprobante',
        'FECHA PAGO': '/api/rendicion/foto/%d/6/10/2026 14:30:00/rendicion_pago.jpg?v=9' % pid,
        'FOTOS SUSTENTO': json.dumps(['/api/rendicion/foto/%d/6/10/2026 14:30:00/sustento_form_001.jpg' % pid]),
    })
    try:
        from migrations import _migrar_rendicion
        with app.app_context():
            _migrar_rendicion(Proyecto, AppConfig, NucleusData)
            # columna en el esquema
            cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').first()
            assert cfg and 'MOTIVO RECHAZO' in json.loads(cfg.valor)
            # backfill + URLs saneadas
            fila = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one()
            d = json.loads(fila.data_json)
            assert d['MOTIVO RECHAZO'] == 'Falta el comprobante'
            assert '6/10/2026 14:30:00' not in d['FECHA PAGO']
            assert ' ' not in d['FECHA PAGO'] and d['FECHA PAGO'].endswith('rendicion_pago.jpg?v=9')
            assert '6/10/2026 14:30:00' not in d['FOTOS SUSTENTO']
            # idempotente: una segunda pasada no rompe nada
            _migrar_rendicion(Proyecto, AppConfig, NucleusData)
            fila = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one()
            assert json.loads(fila.data_json)['MOTIVO RECHAZO'] == 'Falta el comprobante'
    finally:
        _borrar(app, pid, key)


@pytest.mark.parametrize('estado,extras,principal', [
    ('OBSERVADO', {}, 'CON SUSTENTO'),
    ('OBSERVADO', {'FECHA SUSTENTO': '2026-10-20'}, 'SUSTENTADO'),
    ('ARCHIVADO', {}, 'SUSTENTADO'),
])
def test_migracion_separa_subestado_sin_perder_adjuntos(app, estado, extras, principal):
    from migrations import _migrar_rendicion
    from services.rendicion_estados import etapa_de
    key = 'REND-SUBESTADO-MIGRA'
    pid = _crear(app, key, {'ESTADO': estado, 'FOTO PAGO': '/pago.jpg', **extras})
    try:
        with app.app_context():
            for _ in range(2):
                _migrar_rendicion(Proyecto, AppConfig, NucleusData)
                fila = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one()
                datos = json.loads(fila.data_json)
                assert datos['ESTADO'] == principal
                assert datos['SUBESTADO'] == estado
                assert etapa_de(datos) == estado
                assert datos['FOTO PAGO'] == '/pago.jpg'
            cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='app_schema').one()
            assert 'SUBESTADO' in json.loads(cfg.valor)
    finally:
        _borrar(app, pid, key)
