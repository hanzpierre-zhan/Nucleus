# -*- coding: utf-8 -*-
"""Plantilla Excel de columnas manuales (/api/import/manual_template).

El endpoint pasó de generar el .xlsx con `pandas.to_excel` a escribirlo
directamente con openpyxl (mismo archivo, ~30 % menos de tiempo). Estas pruebas
fijan la estructura del libro: hoja, cabecera, filas, congelado, autofiltro,
anchos y estilos de la cabecera.
"""
import io
import json

import openpyxl

from db import db
from models import AppConfig, NucleusData, Proyecto


def test_plantilla_site_clave_manual_importable(app, auth_client):
    """Una clave incluida en las manuales debe sobrevivir descarga e importación."""
    with app.app_context():
        proyecto = Proyecto(nombre='SITE QA plantilla')
        db.session.add(proyecto)
        db.session.flush()
        pid = proyecto.id
        db.session.add_all([
            AppConfig(proyecto_id=pid, clave='primary_key', valor='Código'),
            AppConfig(proyecto_id=pid, clave='manual_columns',
                      valor=json.dumps([{'nombre': 'Código'}, {'nombre': 'Nombre'}])),
            NucleusData(proyecto_id=pid, key_value='SITE-001',
                        data_json=json.dumps({'Código': 'SITE-001', 'Nombre': 'Original'})),
        ])
        db.session.commit()
    try:
        with auth_client.session_transaction() as ses:
            ses['current_proyecto_id'] = pid
            ses['current_proyecto_nombre'] = 'SITE'
        descarga = auth_client.get('/api/import/manual_template')
        assert descarga.status_code == 200
        assert 'spreadsheetml' in descarga.content_type
        libro = openpyxl.load_workbook(io.BytesIO(descarga.data))
        hoja = libro['Plantilla']
        assert list(hoja.values) == [('Código', 'Nombre'), ('SITE-001', None)]
        hoja['B2'] = 'Actualizado'
        archivo = io.BytesIO()
        libro.save(archivo)
        contenido = archivo.getvalue()
        preview = auth_client.post('/api/import/preview', data={
            'file': (io.BytesIO(contenido), 'plantilla.xlsx')})
        assert preview.status_code == 200
        assert preview.json['columns'] == ['Código', 'Nombre']
        resultado = auth_client.post('/api/import/process', data={
            'type': 'manual_cols', 'file': (io.BytesIO(contenido), 'plantilla.xlsx')})
        assert resultado.status_code == 200, resultado.json
        assert resultado.json['updated'] == 1
        assert resultado.json['added'] == 0
        with app.app_context():
            fila = NucleusData.query.filter_by(proyecto_id=pid).one()
            assert fila.key_value == 'SITE-001'
            assert json.loads(fila.data_json)['Nombre'] == 'Actualizado'
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid).delete()
            AppConfig.query.filter_by(proyecto_id=pid).delete()
            db.session.delete(db.session.get(Proyecto, pid))
            db.session.commit()

DETALLE = [
    'Fecha de creación (WO Creation date)',
    'Nombre de Site',
    'Autin TT',
    'Departamento',
    'Fault Level',
    'Estado de la tarea (WO State)',
    'Prioridad del Site',
    'Provincia',
    'Distrito',
]


def _config_manual(pid, columnas):
    """Deja `manual_columns` con los nombres indicados; devuelve el valor previo."""
    cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    if cfg:
        previo = cfg.valor
        cfg.valor = json.dumps([{'nombre': c} for c in columnas])
        return previo, True
    db.session.add(AppConfig(proyecto_id=pid, clave='manual_columns',
                             valor=json.dumps([{'nombre': c} for c in columnas])))
    return None, False


def _restaurar_manual(pid, previo, existia):
    cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='manual_columns').first()
    if existia:
        cfg.valor = previo
    elif cfg:
        db.session.delete(cfg)


def test_plantilla_flm_estructura_y_estilos(app, auth_client):
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre='FLM - ENTEL').one()
        pk = AppConfig.query.filter_by(proyecto_id=proy.id, clave='primary_key').first()
        pk_name = pk.valor if pk else '_key'
        previo, existia = _config_manual(proy.id, ['Gestión QA', 'SERVICIO'])
        db.session.add(NucleusData(
            proyecto_id=proy.id, key_value='CM-PLANT-QA',
            data_json=json.dumps({'Nombre de Site': 'SITE-QA', 'Gestión QA': 'valor qa'})))
        db.session.commit()
        pid = proy.id
    try:
        with auth_client.session_transaction() as ses:
            ses['current_proyecto_id'] = pid
            ses['current_proyecto_nombre'] = 'FLM - ENTEL'

        r = auth_client.get('/api/import/manual_template')
        assert r.status_code == 200, r.data[:300]
        assert 'spreadsheetml' in r.headers['Content-Type']
        assert 'plantilla_FLM - ENTEL.xlsx' in r.headers['Content-Disposition']

        hoja = openpyxl.load_workbook(io.BytesIO(r.data))['Plantilla']
        cabecera = [c.value for c in hoja[1]]
        assert cabecera == [pk_name] + DETALLE + ['Gestión QA', 'SERVICIO']

        # Fila de datos: PK + detalle + gestión en el mismo orden que la cabecera.
        # Las celdas vacías se leen como None (igual que con pandas.to_excel).
        detalle = {'Nombre de Site': 'SITE-QA'}
        manual = {'Gestión QA': 'valor qa'}
        esperado = tuple(['CM-PLANT-QA'] + [detalle.get(c) for c in DETALLE]
                         + [manual.get(c) for c in ('Gestión QA', 'SERVICIO')])
        filas = {f[0]: f for f in hoja.iter_rows(min_row=2, values_only=True)}
        assert 'CM-PLANT-QA' in filas
        assert filas['CM-PLANT-QA'] == esperado

        # Congelado y autofiltro sobre el rango usado.
        assert hoja.freeze_panes == 'A2'
        assert hoja.auto_filter.ref == hoja.dimensions

        # Cabecera en negrita; Detalle y Gestión con relleno distinto; PK sin relleno.
        for idx, nombre in enumerate(cabecera, 1):
            celda = hoja.cell(row=1, column=idx)
            assert celda.font.bold is True and celda.font.size == 9
            if nombre in DETALLE:
                assert celda.fill.start_color.rgb.endswith('E8F0FE'), nombre
            elif nombre in ('Gestión QA', 'SERVICIO'):
                assert celda.fill.start_color.rgb.endswith('FEF3C7'), nombre
            else:
                assert celda.fill.fill_type is None
    finally:
        with app.app_context():
            NucleusData.query.filter_by(key_value='CM-PLANT-QA').delete()
            _restaurar_manual(pid, previo, existia)
            db.session.commit()


def test_plantilla_generica_sin_estilos(app, auth_client):
    with app.app_context():
        proy = Proyecto.query.filter_by(nombre='Generadores').one()
        pk = AppConfig.query.filter_by(proyecto_id=proy.id, clave='primary_key').first()
        pk_name = pk.valor if pk else '_key'
        db.session.add(NucleusData(
            proyecto_id=proy.id, key_value='GEN-PLANT-QA',
            data_json=json.dumps({'QR ASIGNADO': 'QR-1'})))
        db.session.commit()
        pid = proy.id
    try:
        with auth_client.session_transaction() as ses:
            ses['current_proyecto_id'] = pid
            ses['current_proyecto_nombre'] = 'Generadores'

        r = auth_client.get('/api/import/manual_template')
        assert r.status_code == 200, r.data[:300]
        assert 'plantilla_columnas_manuales.xlsx' in r.headers['Content-Disposition']

        hoja = openpyxl.load_workbook(io.BytesIO(r.data))['Plantilla']
        cabecera = [c.value for c in hoja[1]]
        assert cabecera[0] == pk_name
        # La plantilla genérica no lleva estilos ni congelado ni autofiltro.
        assert hoja.freeze_panes is None
        assert hoja.auto_filter.ref is None
        assert hoja.cell(row=1, column=1).font.bold is not True

        filas = {f[0]: f for f in hoja.iter_rows(min_row=2, values_only=True)}
        assert 'GEN-PLANT-QA' in filas
        # Las columnas manuales van vacías → se leen como None.
        assert filas['GEN-PLANT-QA'] == tuple(['GEN-PLANT-QA'] + [None] * (len(cabecera) - 1))
    finally:
        with app.app_context():
            NucleusData.query.filter_by(key_value='GEN-PLANT-QA').delete()
            db.session.commit()


def test_sites_importa_proyectos_sin_sobrescribir_otros(app, auth_client):
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='SITE').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value='QA-SITE-ENTEL',
                                   data_json=json.dumps({'Código': 'QA-SITE-ENTEL', 'Nombre': 'Original', 'PROYECTO': 'ENTEL'})))
        db.session.commit()
    try:
        with auth_client.session_transaction() as s:
            s.update(current_proyecto_id=pid, current_proyecto_nombre='SITE')
        descarga = auth_client.get('/api/import/manual_template')
        assert descarga.status_code == 200
        hoja = openpyxl.load_workbook(io.BytesIO(descarga.data)).active
        assert 'PROYECTO' in [c.value for c in hoja[1]]
        def cargar(texto):
            return auth_client.post('/api/import/process', data={
                'type': 'manual_cols', 'file': (io.BytesIO(texto.encode('utf-8')), 'sites.csv')})
        assert cargar('Código,Nombre\nQA-SITE-NUEVO,Sin proyecto\n').status_code == 400
        for proyecto in ('CLARO', 'INTEGRATEL', 'PEXT'):
            r = cargar('Código,Nombre,PROYECTO\nQA-SITE-%s,Nuevo,%s\n' % (proyecto, proyecto))
            assert r.status_code == 200, r.json
            assert r.json['added'] == 1
        r = cargar('Código,Nombre,PROYECTO\nQA-SITE-ENTEL,Reemplazo,CLARO\n')
        assert r.status_code == 400
        with app.app_context():
            original = NucleusData.query.filter_by(proyecto_id=pid, key_value='QA-SITE-ENTEL').one()
            assert json.loads(original.data_json)['Nombre'] == 'Original'
            for proyecto in ('CLARO', 'INTEGRATEL', 'PEXT'):
                fila = NucleusData.query.filter_by(proyecto_id=pid, key_value='QA-SITE-' + proyecto).one()
                assert json.loads(fila.data_json)['PROYECTO'] == proyecto
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.proyecto_id == pid, NucleusData.key_value.like('QA-SITE-%')).delete(synchronize_session=False)
            db.session.commit()
