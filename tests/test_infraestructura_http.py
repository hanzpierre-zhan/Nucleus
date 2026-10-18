"""Contratos HTTP que deben mantenerse al separar la infraestructura."""
import gzip
from flask import Flask, Response
from infrastructure.http import _register_error_handlers, _register_compress, _register_no_cache_html


def aplicacion():
    app=Flask(__name__)
    _register_error_handlers(app)
    _register_compress(app)
    _register_no_cache_html(app)
    return app


def test_404_web_y_api_conservan_sus_formatos():
    client=aplicacion().test_client()
    web=client.get('/no-existe')
    api=client.get('/api/no-existe')
    assert web.status_code==404 and web.mimetype=='text/html'
    assert api.status_code==404 and 'error' in api.json


def test_compresion_y_cache_conservan_contenido():
    app=aplicacion()
    @app.get('/pagina')
    def pagina():return '<p>'+('texto '*1000)+'</p>'
    client=app.test_client()
    original=client.get('/pagina')
    comprimida=client.get('/pagina',headers={'Accept-Encoding':'gzip'})
    assert comprimida.headers['Content-Encoding']=='gzip'
    assert gzip.decompress(comprimida.data)==original.data
    assert comprimida.headers['Cache-Control']=='no-cache'
    assert 'Accept-Encoding' in comprimida.headers['Vary']


def test_cache_explicita_y_archivos_binarios_no_se_modifican():
    app=aplicacion()
    @app.get('/archivo')
    def archivo():return Response(b'x'*2000,mimetype='application/octet-stream')
    @app.get('/cache')
    def cache():return Response('html',mimetype='text/html',headers={'Cache-Control':'private, max-age=20'})
    client=app.test_client()
    assert 'Content-Encoding' not in client.get('/archivo',headers={'Accept-Encoding':'gzip'}).headers
    assert client.get('/cache').headers['Cache-Control']=='private, max-age=20'
