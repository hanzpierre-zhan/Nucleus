import io
import json
import zipfile
from pathlib import Path
from db import db
from models import Proyecto, NucleusData


def test_zip_solo_fotos_de_la_wo_y_no_otros_adjuntos(app, auth_client, monkeypatch):
    import blueprints.evidencia as evidencia
    monkeypatch.setattr(evidencia, 'evidencia_usa_b2', lambda: False)
    with app.app_context():
        proyecto=Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one()
        row=NucleusData(proyecto_id=proyecto.id,key_value='CM-FOTOS-QA',data_json=json.dumps({}))
        db.session.add(row);db.session.commit();pid=proyecto.id
        folder=Path(evidencia.evidencia_folder(pid,row.key_value));folder.mkdir(parents=True,exist_ok=True)
        (folder/'inicio_0.jpg').write_bytes(b'foto inicio')
        (folder/'cierre_0.png').write_bytes(b'foto cierre')
        (folder/'proveedor.pdf').write_bytes(b'no es foto')
        (folder/'comb_0.jpg').write_bytes(b'otra pestana')
    with auth_client.session_transaction() as session:
        session['current_proyecto_id']=pid;session['current_proyecto_nombre']='FLM - INTEGRATEL'
    response=auth_client.get(f'/api/evidencia/zip/{pid}/CM-FOTOS-QA?solo_fotos=1')
    assert response.status_code==200 and response.mimetype=='application/zip'
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert set(archive.namelist())=={'CM-FOTOS-QA/inicio_0.jpg','CM-FOTOS-QA/cierre_0.png'}
        assert archive.read('CM-FOTOS-QA/inicio_0.jpg')==b'foto inicio'
    assert auth_client.get(f'/api/evidencia/zip/{pid}/INEXISTENTE?solo_fotos=1').status_code==404
    assert auth_client.get(f'/api/evidencia/zip/{pid+100}/CM-FOTOS-QA?solo_fotos=1').status_code==403


def test_descarga_b2_incluye_fotos_y_excluye_documentos(app, auth_client, monkeypatch):
    import blueprints.evidencia as evidencia
    class Storage:
        def list_objects_v2(self, **kwargs):
            return {'Contents':[{'Key':'CM-B2-QA/proceso_0.jpg'}, {'Key':'CM-B2-QA/factura.pdf'}]}
        def get_object(self, **kwargs):
            assert kwargs['Key']=='CM-B2-QA/proceso_0.jpg'
            return {'Body':io.BytesIO(b'foto b2')}
    monkeypatch.setattr(evidencia,'evidencia_usa_b2',lambda:True)
    monkeypatch.setattr(evidencia,'b2_cliente',lambda:Storage())
    monkeypatch.setitem(app.config,'B2_BUCKET','qa-bucket')
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        db.session.add(NucleusData(proyecto_id=pid,key_value='CM-B2-QA',data_json='{}'));db.session.commit()
    with auth_client.session_transaction() as session:
        session['current_proyecto_id']=pid;session['current_proyecto_nombre']='FLM - INTEGRATEL'
    response=auth_client.get(f'/api/evidencia/zip/{pid}/CM-B2-QA?solo_fotos=1')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.namelist()==['CM-B2-QA/proceso_0.jpg']
        assert archive.read(archive.namelist()[0])==b'foto b2'


def test_boton_descarga_disponible_en_modal_de_evidencia(app, auth_client):
    for nombre, visible in [('FLM - INTEGRATEL',True),('FLM - CLARO',True),('FLM - ENTEL',True),('Cotizaciones',True)]:
        with app.app_context(): pid=Proyecto.query.filter_by(nombre=nombre).one().id
        auth_client.get(f'/switch_project/{pid}')
        response=auth_client.get('/')
        assert response.status_code==200
        assert (b'id="btn-evidencia-zip"' in response.data)==visible


def test_descarga_despues_de_asignar_wo_a_codigo_interno(app,auth_client,monkeypatch):
    import blueprints.evidencia as evidencia
    monkeypatch.setattr(evidencia,'evidencia_usa_b2',lambda:False)
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        origen='CI-INTEG-QA'
        folder=Path(evidencia.evidencia_folder(pid,origen));folder.mkdir(parents=True,exist_ok=True)
        (folder/'inicio_0.jpg').write_bytes(b'foto previa al WO')
        fotos=json.dumps([f'/api/evidencia/foto/{pid}/{origen}/inicio_0.jpg?v=1'])
        db.session.add(NucleusData(proyecto_id=pid,key_value='CM-ASIGNADO-QA',data_json=json.dumps({'_EVIDENCIA_INICIO':fotos})))
        db.session.commit()
    with auth_client.session_transaction() as session:
        session['current_proyecto_id']=pid;session['current_proyecto_nombre']='FLM - INTEGRATEL'
    response=auth_client.get(f'/api/evidencia/zip/{pid}/CM-ASIGNADO-QA?solo_fotos=1')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.namelist()==['CM-ASIGNADO-QA/inicio_01.jpg']
        assert archive.read(archive.namelist()[0])==b'foto previa al WO'


def test_foto_b2_legacy_clave_cruda_con_url_saneada(app, auth_client, monkeypatch):
    import blueprints.evidencia as evidencia
    from werkzeug.utils import secure_filename
    key = 'QA WO con espacios'
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value=key, data_json='{}'))
        db.session.commit()
    with auth_client.session_transaction() as s:
        s.update(current_proyecto_id=pid, current_proyecto_nombre='FLM - INTEGRATEL')
    class B2:
        def get_object(self, Bucket, Key):
            if Key != key + '/inicio_0.jpg':
                raise KeyError(Key)
            return {'Body': io.BytesIO(b'foto antigua')}
    monkeypatch.setattr(evidencia, 'evidencia_usa_b2', lambda: True)
    monkeypatch.setattr(evidencia, 'b2_cliente', lambda: B2())
    monkeypatch.setitem(app.config, 'B2_BUCKET', 'prueba')
    try:
        r = auth_client.get('/api/evidencia/foto/%s/%s/inicio_0.jpg' % (pid, secure_filename(key)))
        assert r.status_code == 200
        assert r.data == b'foto antigua'
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid, key_value=key).delete()
            db.session.commit()


def test_fallo_subida_b2_wo_no_elimina_foto_existente(app, auth_client, monkeypatch):
    import blueprints.evidencia as evidencia
    key = 'QA-B2-REEMPLAZO'
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        db.session.add(NucleusData(proyecto_id=pid, key_value=key, data_json='{}'))
        db.session.commit()
    with auth_client.session_transaction() as s:
        s.update(current_proyecto_id=pid, current_proyecto_nombre='FLM - INTEGRATEL')
    limpiezas = []
    class B2:
        def upload_file(self, *args):
            raise OSError('fallo simulado')
    monkeypatch.setattr(evidencia, 'evidencia_usa_b2', lambda: True)
    monkeypatch.setattr(evidencia, 'b2_cliente', lambda: B2())
    monkeypatch.setattr(evidencia, 'evidencia_eliminar_b2', lambda *a, **k: limpiezas.append(a))
    monkeypatch.setattr(evidencia, 'evidencia_comprimir', lambda ruta: False)
    monkeypatch.setitem(app.config, 'B2_BUCKET', 'prueba')
    try:
        r = auth_client.post('/api/evidencia/subir', data={
            'key': key, 'tipo': 'inicio', 'indice': '0', 'foto': (io.BytesIO(b'nueva'), 'foto.jpg')})
        assert r.status_code == 500
        assert limpiezas == []
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid, key_value=key).delete()
            db.session.commit()
