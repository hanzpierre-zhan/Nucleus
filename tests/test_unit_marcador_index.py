# -*- coding: utf-8 -*-
"""Invariantes de la técnica del marcador en `/` (`blueprints/pages.py`).

El endpoint serializa los datos y los inserta con
`html.replace(_MARCADOR_DATOS_TABLA, datos_json)`. Estas pruebas fijan las
invariantes de esa técnica sin cambiar el HTML servido.

Capa 1/2 de la estrategia (`docs/estrategia_testing.md` §3.8).
"""
import json

from db import db
from models import NucleusData, Proyecto

_MARCA = 'const rawData = '
_MARCADOR_INTERNO = '__NUCLEUS_DATOS_TABLA_9f4c1a__'


def _datos_incrustados(html):
    """Devuelve el JSON que sigue a `const rawData = ` dentro del HTML."""
    inicio = html.index(_MARCA) + len(_MARCA)
    datos, _ = json.JSONDecoder().raw_decode(html, inicio)
    return datos


def test_el_marcador_se_sustituye_una_sola_vez(app, auth_client):
    """Si la plantilla imprimiera `data` dos veces, el JSON se duplicaría."""
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
    auth_client.get('/switch_project/%s' % pid)
    pagina = auth_client.get('/')
    assert pagina.status_code == 200
    html = pagina.get_data(as_text=True)
    assert html.count(_MARCA) == 1
    assert isinstance(_datos_incrustados(html), list)


def test_un_valor_que_contiene_el_marcador_no_corrompe_los_datos(app, auth_client):
    """`str.replace` no re-escanea el texto insertado: un valor que coincida con
    el marcador interno se conserva tal cual y el JSON se inserta una sola vez."""
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        db.session.add(NucleusData(
            proyecto_id=pid, key_value='CM-MARCADOR-QA',
            data_json=json.dumps({'Número de WO': 'CM-MARCADOR-QA',
                                  'Comentario': _MARCADOR_INTERNO})))
        db.session.commit()
    try:
        auth_client.get('/switch_project/%s' % pid)
        pagina = auth_client.get('/')
        assert pagina.status_code == 200
        html = pagina.get_data(as_text=True)
        assert html.count(_MARCA) == 1
        tabla = _datos_incrustados(html)
        fila = next(f for f in tabla if f.get('_key') == 'CM-MARCADOR-QA')
        assert fila.get('Comentario') == _MARCADOR_INTERNO
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid,
                                        key_value='CM-MARCADOR-QA').delete()
            db.session.commit()
