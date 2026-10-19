import io
import json

import pytest
from werkzeug.utils import secure_filename

from db import db
from models import NucleusData, Proyecto


@pytest.fixture
def foto_form(app, auth_client, monkeypatch):
    import blueprints.rendicion as rend
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Rendicion').one().id
        fila = NucleusData(proyecto_id=pid, key_value='1/10/2026 16:40:09',
                           data_json=json.dumps({'PROYECTO': 'ENTEL', 'CODIGO DEPOSITO': 'QA-FOTO-COB-00031'}))
        db.session.add(fila)
        db.session.commit()
        rid = fila.id
    with auth_client.session_transaction() as s:
        s.update(current_proyecto_id=pid, current_proyecto_nombre='Rendicion')
    monkeypatch.setattr(rend, 'evidencia_usa_b2', lambda: True)
    monkeypatch.setitem(app.config, 'B2_BUCKET', 'prueba')
    yield rend, pid, '1/10/2026 16:40:09'
    with app.app_context():
        db.session.delete(db.session.get(NucleusData, rid))
        db.session.commit()


@pytest.mark.parametrize('historica', [True, False])
def test_foto_form_recupera_archivo_b2_con_url_saneada(auth_client, monkeypatch, foto_form, historica):
    rend, pid, key = foto_form
    nombre = 'sustento_form_001.jpg'
    objeto = (key if historica else secure_filename(key)) + '/' + nombre
    class B2:
        def get_object(self, Bucket, Key):
            if Key != objeto:
                raise KeyError(Key)
            return {'Body': io.BytesIO(b'imagen-recuperada')}
    monkeypatch.setattr(rend, 'b2_cliente', lambda: B2())
    r = auth_client.get('/api/rendicion/foto/%s/%s/%s' % (pid, secure_filename(key), nombre))
    assert r.status_code == 200
    assert r.data == b'imagen-recuperada'
    assert r.mimetype == 'image/jpeg'


def test_nueva_copia_form_guarda_con_misma_clave_que_url(app, auth_client, monkeypatch, foto_form, tmp_path):
    rend, pid, key = foto_form
    temporal = tmp_path / 'foto.jpg'
    temporal.write_bytes(b'foto-prueba')
    objetos = {}
    class B2:
        def upload_file(self, ruta, bucket, clave):
            objetos[clave] = open(ruta, 'rb').read()
        def get_object(self, Bucket, Key):
            return {'Body': io.BytesIO(objetos[Key])}
    monkeypatch.setattr(rend, 'b2_cliente', lambda: B2())
    monkeypatch.setattr(rend, '_bajar_foto_form', lambda url: (str(temporal), '.jpg'))
    monkeypatch.setattr(rend, 'evidencia_comprimir', lambda ruta: None)
    row = {'SUSTENTO_VIATICOS': 'https://example.test/adjunto.jpg'}
    with app.test_request_context('/'):
        assert rend._persistir_fotos_form(pid, key, row) == 1
    assert len(objetos) == 1
    assert next(iter(objetos)).startswith(secure_filename(key) + '/sustento_form_')
    r = auth_client.get(row['SUSTENTO_VIATICOS'])
    assert r.status_code == 200
    assert r.data == b'foto-prueba'


def test_reemplazo_foto_b2_fallido_no_borra_la_anterior(app, auth_client, monkeypatch, foto_form):
    rend, pid, key = foto_form
    eliminaciones = []
    class B2:
        def upload_file(self, *args):
            raise OSError('fallo simulado')
        def list_objects_v2(self, **kwargs):
            return {'Contents': [{'Key': secure_filename(key) + '/rendicion_pago.jpg'}]}
        def delete_object(self, **kwargs):
            eliminaciones.append(kwargs)
    monkeypatch.setattr(rend, 'b2_cliente', lambda: B2())
    monkeypatch.setattr(rend, 'evidencia_comprimir', lambda ruta: None)
    r = auth_client.post('/api/rendicion/subir_foto', data={
        'key': key, 'slot': 'pago', 'foto': (io.BytesIO(b'nueva foto'), 'foto.jpg')})
    assert r.status_code == 500
    assert eliminaciones == []


def test_lectura_local_respeta_directorio_configurado(app, auth_client, monkeypatch, foto_form, tmp_path):
    rend, pid, key = foto_form
    monkeypatch.setattr(rend, 'evidencia_usa_b2', lambda: False)
    monkeypatch.setitem(app.config, 'EVIDENCIA_DIR', str(tmp_path))
    carpeta = tmp_path / str(pid) / secure_filename(key)
    carpeta.mkdir(parents=True)
    (carpeta / 'rendicion_pago.jpg').write_bytes(b'foto en disco persistente')
    r = auth_client.get('/api/rendicion/foto/%s/%s/rendicion_pago.jpg' % (pid, secure_filename(key)))
    assert r.status_code == 200
    assert r.data == b'foto en disco persistente'


def test_descarga_form_no_confunde_pagina_de_acceso_con_foto(monkeypatch):
    import blueprints.rendicion as rend
    monkeypatch.setattr(rend.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'<html>Iniciar sesion en Google</html>'))
    assert rend._bajar_foto_form('https://example.test/drive') == (None, None)


def test_descarga_form_identifica_formato_real(monkeypatch):
    import blueprints.rendicion as rend
    from PIL import Image
    contenido = io.BytesIO()
    Image.new('RGB', (2, 2)).save(contenido, format='PNG')
    monkeypatch.setattr(rend.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(contenido.getvalue()))
    ruta, extension = rend._bajar_foto_form('https://example.test/foto')
    try:
        assert extension == '.png'
        with open(ruta, 'rb') as archivo:
            assert archivo.read() == contenido.getvalue()
    finally:
        if ruta:
            import os
            os.remove(ruta)


def test_cuota_b2_agotada_no_se_informa_como_archivo_perdido(auth_client, monkeypatch, foto_form):
    rend, pid, key = foto_form
    class CuotaAgotada(Exception):
        response = {'Error': {'Code': 'AccessDenied', 'Message': 'download bandwidth or transaction (Class B) cap exceeded'}}
    class B2:
        def get_object(self, **kwargs):
            raise CuotaAgotada()
    monkeypatch.setattr(rend, 'b2_cliente', lambda: B2())
    r = auth_client.get('/api/rendicion/foto/%s/%s/sustento_form_001.jpg' % (pid, secure_filename(key)))
    assert r.status_code == 503
    assert 'límite diario' in r.json['error']


def test_descarga_form_conserva_pdf_completo(monkeypatch):
    import blueprints.rendicion as rend
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader
    pdf = io.BytesIO()
    documento = canvas.Canvas(pdf)
    documento.drawString(10, 100, 'Pagina uno'); documento.showPage()
    documento.drawString(10, 100, 'Pagina dos'); documento.save()
    monkeypatch.setattr(rend.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(pdf.getvalue()))
    ruta, extension = rend._bajar_foto_form('https://example.test/adjunto')
    try:
        assert extension == '.pdf'
        assert len(PdfReader(ruta).pages) == 2
    finally:
        if ruta:
            import os
            os.remove(ruta)
