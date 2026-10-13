import json
from db import db
from models import AppConfig, NucleusData, Proyecto
from services.utilidades import ahora_peru


def test_prefijos_comparten_secuencia_historica_y_evitan_reusar_numero(app, auth_client):
    year = ahora_peru().year
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='cotizacion_next_seq').first()
        original = cfg.valor if cfg else None
        if not cfg:
            cfg = AppConfig(proyecto_id=pid, clave='cotizacion_next_seq')
            db.session.add(cfg)
        cfg.valor = '9000002'
        old_key = f'HW-{year}-9000001'
        db.session.add(NucleusData(proyecto_id=pid, key_value=old_key,
                                  data_json=json.dumps({'N° COTIZACION':old_key,'CLIENTE':'ENTEL'})))
        db.session.commit()
    auth_client.get(f'/switch_project/{pid}')
    keys = [old_key]
    try:
        for index, (client, prefix) in enumerate([('ENTEL','EN'),('CLARO','CL'),('INTEGRATEL','IN')]):
            # A stale suggestion must not reuse the historical sequence under a new prefix.
            response = auth_client.post('/api/rows/add', json={'key':'', 'data':{
                'CLIENTE':client, 'N° COTIZACION':old_key if index == 0 else '',
            }})
            assert response.status_code == 200, response.json
            key = response.json['key']; keys.append(key)
            assert key == f'{prefix}-{year}-{9000002+index:07d}'
            with app.app_context():
                row = NucleusData.query.filter_by(proyecto_id=pid, key_value=key).one()
                assert json.loads(row.data_json)['N° COTIZACION'] == key
        with app.app_context():
            assert NucleusData.query.filter_by(proyecto_id=pid,key_value=old_key).one()
            assert AppConfig.query.filter_by(proyecto_id=pid,clave='cotizacion_next_seq').one().valor == '9000005'
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.proyecto_id==pid,NucleusData.key_value.in_(keys)).delete(synchronize_session=False)
            cfg = AppConfig.query.filter_by(proyecto_id=pid,clave='cotizacion_next_seq').one()
            if original is None: db.session.delete(cfg)
            else: cfg.valor = original
            db.session.commit()


def test_pdf_responsable_juan_balarezo(app):
    import base64
    import re
    import zlib
    from services.apoyo import _generar_pdf_cotizacion_cobra
    with app.app_context():
        pdf = _generar_pdf_cotizacion_cobra(numero='EN-2026-0000342',site='SITE TEST',
            supervisor='SUPERVISOR',objetivo='PRUEBA',ticket='CM-TEST',
            elaborado_por='USUARIO',items=[],fecha='2026-10-13')
    streams = []
    for stream in re.findall(rb'stream\r?\n(.*?)endstream',pdf,re.S):
        try:
            streams.append(zlib.decompress(base64.a85decode(stream.strip(),adobe=True)))
        except (ValueError,zlib.error):
            continue
    text = b'\n'.join(streams)
    assert b'Juan Balarezo' in text
    assert b'Dennis Unton' not in text
