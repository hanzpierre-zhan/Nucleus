# -*- coding: utf-8 -*-
"""Barrido de rutas: ninguna ruta GET sin parámetros debe devolver un 5xx.

Capa 2 de la estrategia (docs/estrategia_testing.md §4.12). Es una red de
seguridad amplia: recorre de una a una todas las rutas GET que no llevan
parámetros en la URL y exige que ninguna responda con un error de servidor.

Para que el barrido sea inocuo se excluyen las rutas que salen a la red,
escriben en la base o tocan el disco (esas tienen su propia prueba aparte).
"""
from models import Proyecto

# Rutas excluidas y por qué:
EXCLUIDAS = {
    '/api/rendicion/sync',           # descarga externa (Google Sheets)
    '/api/cotizacion/next_seq',      # crea/actualiza la secuencia de cotización
    '/api/admin/export_zip',         # genera y escribe un ZIP en disco
    '/api/import/manual_template',   # cubierta por su propio golden
    '/api/autin/config',             # lee rutas/servidor de fotos del disco
    '/api/autin/foto',
    '/api/autin/fotos',
    '/api/autin/zip',
}

# Respuestas que NO son 2xx/3xx/4xx pero son legítimas y están documentadas:
#   blueprints/evidencia.py:447 devuelve 503 ("servicio no disponible") cuando
#   el proyecto todavía no tiene configurado el reporte de evidencia.
PERMITIDOS = {'/api/evidencia/reporte_config': (200, 503)}


def _rutas_get_sin_parametros(app):
    return sorted({
        str(regla) for regla in app.url_map.iter_rules()
        if 'GET' in regla.methods
        and '<' not in str(regla)
        and not str(regla).startswith(('/static', '/logout'))
    })


def test_ninguna_ruta_get_sin_parametros_devuelve_5xx(app, auth_client):
    rutas = [r for r in _rutas_get_sin_parametros(app) if r not in EXCLUIDAS]
    assert len(rutas) > 60, 'el barrido debe cubrir la mayoría de las rutas'

    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
    auth_client.get('/switch_project/%s' % pid)

    fallos = []
    for ruta in rutas:
        codigo = auth_client.get(ruta).status_code
        permitidos = PERMITIDOS.get(ruta)
        if permitidos is not None:
            if codigo not in permitidos:
                fallos.append((ruta, codigo))
        elif codigo >= 500:
            fallos.append((ruta, codigo))

    assert not fallos, 'rutas con error de servidor (5xx): %s' % fallos
