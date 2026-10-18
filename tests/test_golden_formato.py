# -*- coding: utf-8 -*-
"""Golden de formato: la plantilla Excel y el contrato de datos de '/'.

Capa 3 de la estrategia (docs/estrategia_testing.md §3 y §4.8). Congela el
*formato* de dos salidas que se generan de forma dinámica, que es justo lo que
no debe cambiar:

  * la plantilla de columnas manuales (`/api/import/manual_template`): hoja,
    cabecera, celdas y anchos, y que el archivo sea idéntico entre llamadas;
  * el JSON de datos que '/' incrusta para la tabla (`const rawData = ...`).

Para no depender de datos compartidos, cada prueba crea su propio proyecto
temporal y lo borra al terminar.
"""
import io
import json

import openpyxl
import pytest

from db import db
from models import AppConfig, NucleusData, Proyecto

_MARCA = 'const rawData = '


def _datos_incrustados(html):
    """Devuelve el JSON que sigue a `const rawData = ` dentro del HTML."""
    inicio = html.index(_MARCA) + len(_MARCA)
    datos, _ = json.JSONDecoder().raw_decode(html, inicio)
    return datos


@pytest.fixture()
def proyecto_qa(app):
    """Proyecto aislado con 2 filas y las columnas manuales configuradas."""
    with app.app_context():
        proyecto = Proyecto(nombre='QA-GOLDEN')
        db.session.add(proyecto)
        db.session.flush()
        pid = proyecto.id
        db.session.add(AppConfig(proyecto_id=pid, clave='primary_key', valor='CODIGO'))
        db.session.add(AppConfig(
            proyecto_id=pid, clave='manual_columns',
            valor=json.dumps([{'nombre': 'Comentario'}, {'nombre': 'Estado'}])))
        for clave in ('G-1', 'G-2'):
            db.session.add(NucleusData(
                proyecto_id=pid, key_value=clave,
                data_json=json.dumps({'Número de WO': clave})))
        db.session.commit()
    try:
        yield pid
    finally:
        with app.app_context():
            AppConfig.query.filter_by(proyecto_id=pid).delete()
            NucleusData.query.filter_by(proyecto_id=pid).delete()
            Proyecto.query.filter_by(id=pid).delete()
            db.session.commit()


def test_plantilla_columnas_manuales_formato_estable(app, auth_client, proyecto_qa):
    auth_client.get('/switch_project/%s' % proyecto_qa)

    primera = auth_client.get('/api/import/manual_template')
    segunda = auth_client.get('/api/import/manual_template')
    assert primera.status_code == 200
    assert primera.mimetype in (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/octet-stream')

    # El archivo es determinista: dos llamadas dan exactamente los mismos bytes.
    assert primera.get_data() == segunda.get_data()

    hoja = openpyxl.load_workbook(io.BytesIO(primera.get_data())).active
    assert hoja.title == 'Plantilla'
    assert [[celda.value for celda in fila] for fila in hoja.iter_rows()] == [
        ['CODIGO', 'Comentario', 'Estado'],
        ['G-1', None, None],
        ['G-2', None, None],
    ]
    # Sin congelar paneles ni autofiltro (formato del proyecto genérico).
    assert hoja.freeze_panes is None
    assert hoja.auto_filter.ref is None
    # Anchos de columna = longitud del texto más largo + 4.
    assert hoja.column_dimensions['A'].width == len('CODIGO') + 4
    assert hoja.column_dimensions['B'].width == len('Comentario') + 4
    assert hoja.column_dimensions['C'].width == len('Estado') + 4


def test_datos_de_la_tabla_conservan_su_contrato(app, auth_client, proyecto_qa):
    auth_client.get('/switch_project/%s' % proyecto_qa)
    pagina = auth_client.get('/')
    assert pagina.status_code == 200
    assert b'__NUCLEUS_DATOS_TABLA' not in pagina.data, 'el marcador se filtró al HTML'

    tabla = _datos_incrustados(pagina.get_data(as_text=True))
    assert isinstance(tabla, list)
    assert sorted(fila['_key'] for fila in tabla) == ['G-1', 'G-2']
    for fila in tabla:
        assert fila['Número de WO'] == fila['_key']
