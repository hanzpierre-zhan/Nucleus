# -*- coding: utf-8 -*-
"""Respaldo completo (/api/admin/export_zip).

El endpoint pasó de acumular cada tabla en memoria a escribir el JSON por lotes
dentro del ZIP. Estas pruebas garantizan que el ZIP sigue siendo válido, que el
manifest cuenta todas las filas y que un archivo por proyecto lleva los datos.
"""
import io
import json
import zipfile

from db import db
from models import Proyecto, NucleusData


def test_export_zip_estructura_conteos_y_contenido(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        db.session.add(NucleusData(
            proyecto_id=pid, key_value='CM-EXPORT-QA',
            data_json=json.dumps({'Número de WO': 'CM-EXPORT-QA'})))
        db.session.commit()
        total_data = NucleusData.query.count()
        total_proyectos = Proyecto.query.count()
    try:
        r = auth_client.get('/api/admin/export_zip')
        assert r.status_code == 200
        assert 'zip' in (r.headers.get('Content-Type') or '').lower()

        with zipfile.ZipFile(io.BytesIO(r.data)) as zf:
            assert zf.testzip() is None  # ZIP íntegro

            manifiesto = json.loads(zf.read('manifest.json'))
            assert manifiesto['tablas']['nucleus_data'] == total_data
            assert manifiesto['tablas']['proyectos'] == total_proyectos
            assert manifiesto['proyecto_por_id'][str(pid)] == 'FLM - ENTEL'

            nombres = zf.namelist()
            assert 'proyectos.json' in nombres
            archivos_data = sorted(n for n in nombres if n.startswith('nucleus_data_p'))
            assert archivos_data, 'debe haber un archivo por proyecto con datos'

            filas = []
            for archivo in archivos_data:
                contenido = json.loads(zf.read(archivo))
                assert isinstance(contenido, list)
                filas.extend(contenido)
            assert len(filas) == total_data
            assert {'id', 'proyecto_id', 'key_value', 'data_json'} <= set(filas[0])
            assert any(f.get('key_value') == 'CM-EXPORT-QA' for f in filas)
    finally:
        with app.app_context():
            NucleusData.query.filter_by(key_value='CM-EXPORT-QA').delete()
            db.session.commit()
