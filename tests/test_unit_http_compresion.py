# -*- coding: utf-8 -*-
"""Unitarios de la compresión HTTP (`infrastructure/http.py`).

Se prueba el manejador sobre una app Flask mínima y AISLADA: no toca la app real
ni el formato de ninguna respuesta existente.

Capa 1 de la estrategia (`docs/estrategia_testing.md` §3.7).
"""
import gzip

from flask import Flask, Response

from infrastructure.http import _register_compress


def _app_con_cuerpo(cuerpo, ctype):
    app = Flask(__name__)
    _register_compress(app)

    @app.route('/x')
    def _x():
        return Response(cuerpo, mimetype=ctype)

    return app


def _get(cuerpo, ctype, accept_encoding='gzip'):
    app = _app_con_cuerpo(cuerpo, ctype)
    with app.test_client() as cliente:
        return cliente.get('/x', headers={'Accept-Encoding': accept_encoding})


def test_no_comprime_si_el_cliente_no_acepta_gzip():
    cuerpo = b'x' * 5000
    respuesta = _get(cuerpo, 'application/json', accept_encoding='identity')
    assert 'Content-Encoding' not in respuesta.headers
    assert respuesta.get_data() == cuerpo


def test_comprime_json_grande_y_el_contenido_se_recupera():
    cuerpo = b'{"a":1,"b":"' + b'x' * 5000 + b'"}'
    respuesta = _get(cuerpo, 'application/json')
    assert respuesta.headers.get('Content-Encoding') == 'gzip'
    assert 'Accept-Encoding' in respuesta.headers.get('Vary', '')
    assert gzip.decompress(respuesta.get_data()) == cuerpo


def test_no_comprime_cuerpo_pequeno():
    """Límite: por debajo de 1024 bytes no se comprime."""
    cuerpo = b'{"ok":true}'
    respuesta = _get(cuerpo, 'application/json')
    assert 'Content-Encoding' not in respuesta.headers


def test_no_comprime_tipos_binarios():
    """Límite: solo tipos textuales se comprimen."""
    cuerpo = b'\x89PNG\r\n' + b'0' * 5000
    respuesta = _get(cuerpo, 'image/png')
    assert 'Content-Encoding' not in respuesta.headers
