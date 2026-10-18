# -*- coding: utf-8 -*-
"""El HTML de '/' debe seguir incrustando los datos de la tabla.

`pages.index` serializa los datos y los inserta en el HTML con un marcador que
se sustituye antes de responder (evita que Jinja copie el string gigante varias
veces). Estas pruebas garantizan que los datos llegan al navegador y que el
marcador interno nunca se filtra.
"""
import json

from db import db
from models import Proyecto, NucleusData

_MARCA = 'const rawData = '


def _datos_incrustados(html):
    """Devuelve el JSON que sigue a `const rawData = ` dentro del HTML."""
    inicio = html.index(_MARCA) + len(_MARCA)
    datos, _ = json.JSONDecoder().raw_decode(html, inicio)
    return datos


def test_index_incrusta_datos_sin_filtrar_marcador(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        db.session.add(NucleusData(
            proyecto_id=pid, key_value='CM-INDEX-DATOS-QA',
            data_json=json.dumps({'Número de WO': 'CM-INDEX-DATOS-QA'})))
        db.session.commit()
    try:
        auth_client.get('/switch_project/%s' % pid)
        pagina = auth_client.get('/')
        assert pagina.status_code == 200
        assert b'__NUCLEUS_DATOS_TABLA' not in pagina.data, 'el marcador se filtró al HTML'
        tabla = _datos_incrustados(pagina.get_data(as_text=True))
        assert isinstance(tabla, list)
        assert any(fila.get('_key') == 'CM-INDEX-DATOS-QA' for fila in tabla)
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid, key_value='CM-INDEX-DATOS-QA').delete()
            db.session.commit()
