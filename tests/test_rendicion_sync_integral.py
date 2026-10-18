import io
import json
from db import db
from models import AppConfig, Proyecto, NucleusData


def test_importacion_repetida_conserva_solicitud_y_sustento(app, auth_client, monkeypatch):
    """Ambos formularios ingresan una vez y respetan correcciones locales."""
    import blueprints.admin as admin
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Rendicion').one().id
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave='rendicion_csv_url').first()
        if cfg is None:
            cfg = AppConfig(proyecto_id=pid, clave='rendicion_csv_url')
            db.session.add(cfg)
        cfg.valor = 'https://example.test/solicitudes.csv'
        db.session.commit()
    solicitud = 'Marca temporal,Nombre del proyecto,Observaciones,ESTADO,CODIGO DEPOSITO\nSYNC-INTEGRAL,Claro,Original,ANULADO,EXTERNO\n'
    monkeypatch.setattr(admin.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(solicitud.encode()))
    r = auth_client.post('/api/rendicion/sync')
    assert r.status_code == 200 and r.json['nuevas'] == 1
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value='SYNC-INTEGRAL').one()
        datos = json.loads(fila.data_json)
        assert datos['ESTADO (Form)'] == 'ANULADO' and 'ESTADO' not in datos
        assert datos['Observaciones (Form)'] == 'Original'
        datos.update({'ESTADO': 'DEPOSITADO', 'CODIGO DEPOSITO': 'SYNC-DEP-001', 'MONTO PAGO': '100'})
        fila.data_json = json.dumps(datos)
        db.session.commit()
    assert auth_client.post('/api/rendicion/sync').json['nuevas'] == 0
    sustento = 'Marca temporal,Codigo deposito,Comentario\nSYNC-ENVIO-1,SYNC-DEP-001,Comprobante recibido\nSYNC-ENVIO-2,INEXISTENTE,Sin cruce\n'
    monkeypatch.setattr(admin.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(sustento.encode()))
    r = auth_client.post('/api/rendicion/sync_sustentos')
    assert r.status_code == 200 and r.json['actualizados'] == 1 and r.json['no_encontrados'] == 1
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value='SYNC-INTEGRAL').one()
        datos = json.loads(fila.data_json)
        assert datos['ESTADO'] == 'CON SUSTENTO' and datos['MONTO PAGO'] == '100'
        datos['SUSTENTO_COMENTARIO'] = 'Corregido en Nucleus'
        fila.data_json = json.dumps(datos)
        db.session.commit()
    assert auth_client.post('/api/rendicion/sync_sustentos').json['actualizados'] == 0
    with app.app_context():
        fila = NucleusData.query.filter_by(proyecto_id=pid, key_value='SYNC-INTEGRAL').one()
        assert json.loads(fila.data_json)['SUSTENTO_COMENTARIO'] == 'Corregido en Nucleus'
        db.session.delete(fila)
        db.session.commit()
