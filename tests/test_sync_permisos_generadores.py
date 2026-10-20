import io
import json
import pytest
from db import db
from models import AccesoProyecto, AppConfig, NucleusData, Proyecto, Usuario


@pytest.fixture
def usuario_modulo(app, client):
    with app.app_context():
        ids = {p.nombre:p.id for p in Proyecto.query.all()}
        u = Usuario(username='sync-modulo-regresion', password_hash='no-login', rol='gestor')
        db.session.add(u); db.session.flush(); uid=u.id
        for nombre in ('Rendicion', 'Generadores', 'Combustible', 'Dataper', 'FLM - ENTEL'):
            db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=ids[nombre], restricciones='{}'))
        cfg=AppConfig.query.filter_by(proyecto_id=ids['Rendicion'],clave='rendicion_csv_url').first()
        anterior=cfg.valor if cfg else None
        if cfg is None:
            cfg=AppConfig(proyecto_id=ids['Rendicion'],clave='rendicion_csv_url');db.session.add(cfg)
        cfg.valor='https://example.test/regresion.csv'
        db.session.commit()
    with client.session_transaction() as s:
        s.update(user_id=uid, username='sync-modulo-regresion', rol='gestor', current_proyecto_id=ids['Rendicion'],current_proyecto_nombre='Rendicion')
    yield client, ids, uid
    with app.app_context():
        db.session.rollback()
        NucleusData.query.filter(NucleusData.key_value.like('REG-SYNC-%')).delete(synchronize_session=False)
        cfg=AppConfig.query.filter_by(proyecto_id=ids['Rendicion'],clave='rendicion_csv_url').one()
        if anterior is None:db.session.delete(cfg)
        else:cfg.valor=anterior
        AccesoProyecto.query.filter_by(usuario_id=uid).delete()
        db.session.delete(db.session.get(Usuario,uid));db.session.commit()


@pytest.mark.parametrize('rol,solo_modulo', [('gestor',False),('supervisor',False),('suport',False),('gestor',True)])
def test_sync_global_para_gestor_sin_ampliar_edicion(app, usuario_modulo, monkeypatch,rol,solo_modulo):
    import blueprints.rendicion as flujo
    c,ids,uid=usuario_modulo
    with app.app_context():
        db.session.get(Usuario,uid).rol=rol
        if solo_modulo:
            AccesoProyecto.query.filter_by(usuario_id=uid,proyecto_id=ids['FLM - ENTEL']).delete()
        db.session.commit()
    solicitudes='Marca temporal,Nombre del proyecto,Documento del beneficiario,Tecnico beneficiario\nREG-SYNC-EN,Entel,REG-SYNC-DOC,Escrito\nREG-SYNC-CL,Claro,REG-SYNC-DOC,Escrito\n'
    with app.app_context():
        db.session.add(NucleusData(proyecto_id=ids['Dataper'],key_value='REG-SYNC-PERSONAL',data_json=json.dumps({'PROYECTO':'CLARO','DOCUMENTO':'REG-SYNC-DOC','TECNICO':'Nombre oficial','DEPARTAMENTO':'LIMA'})))
        db.session.commit()
    monkeypatch.setattr(flujo.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(solicitudes.encode()))
    for _ in range(2):
        r=c.post('/api/rendicion/sync')
        assert r.status_code==200,r.text
        assert r.json['nuevas']==(2 if _==0 else 0)
    with app.app_context():
        rows=NucleusData.query.filter_by(proyecto_id=ids['Rendicion']).filter(NucleusData.key_value.like('REG-SYNC-%')).all()
        assert len(rows)==2
        for row in rows:
            d=json.loads(row.data_json)
            assert d['Técnico beneficiario']=='Nombre oficial'
            assert d['DEPARTAMENTO']=='LIMA'
            d.update({'ESTADO':'DEPOSITADO','CODIGO DEPOSITO':row.key_value})
            row.data_json=json.dumps(d)
        db.session.commit()
    sustentos='Marca temporal,Codigo deposito,Comentario\nREG-SYNC-ENVIO,REG-SYNC-CL,Recibido\n'
    monkeypatch.setattr(flujo.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(sustentos.encode()))
    r=c.post('/api/rendicion/sync_sustentos')
    assert r.status_code==200 and r.json['actualizados']==1,r.text
    assert c.post('/api/rendicion/sync_sustentos').json['actualizados']==0
    # La excepción solo vive dentro del importador, no sirve para editar un caso ajeno.
    assert c.post('/api/rows/update',json={'key':'REG-SYNC-CL','field':'DEPARTAMENTO','value':'OTRO'}).status_code==404
    with app.app_context():
        d=json.loads(NucleusData.query.filter_by(proyecto_id=ids['Rendicion'],key_value='REG-SYNC-CL').one().data_json)
        assert d['ESTADO']=='CON SUSTENTO' and d['DEPARTAMENTO']=='LIMA'


def test_generador_sin_clave_y_tecnicos_desde_personal(app,usuario_modulo):
    c,ids,uid=usuario_modulo
    with app.app_context():
        db.session.add(NucleusData(proyecto_id=ids['Dataper'],key_value='REG-SYNC-TECNICO',data_json=json.dumps({'PROYECTO':'ENTEL','TECNICO':'Tecnico del maestro','ESTADO':'ACTIVO'})))
        # Un ID de otro proyecto es invisible para este gestor, pero ocupa la
        # misma clave única. Las altas no deben calcular ID desde filas visibles.
        ocupado=NucleusData(proyecto_id=ids['Generadores'],key_value='1',data_json=json.dumps({'PROYECTO':'CLARO','QR ASIGNADO':'REG-SYNC-OCULTO'}))
        db.session.add(ocupado)
        db.session.commit()
    c.get('/switch_project/%s'%ids['Generadores'])
    pagina=c.get('/')
    assert pagina.status_code==200 and 'Tecnico del maestro' in pagina.text
    campos=c.get('/api/master/manual_columns/options').json['campos']
    assert not any(x['nombre']=='TECNICO ASIGNADO' for x in campos)
    r=c.post('/api/rows/add',json={'key':'','data':{'PROYECTO':'ENTEL','QR ASIGNADO':'REG-SYNC-QR','TECNICO ASIGNADO':'Tecnico del maestro','TIPO':'PROPIO'}})
    assert r.status_code==200,r.text
    with app.app_context():
        row=NucleusData.query.filter_by(proyecto_id=ids['Generadores']).filter(NucleusData.data_json.contains('REG-SYNC-QR')).one()
        assert json.loads(row.data_json)['PROYECTO']=='FLM - ENTEL'
        assert row.key_value.startswith('GEN-')
        db.session.delete(row);db.session.delete(ocupado);db.session.commit()
    # El formulario no ofrece un proyecto que el usuario no puede registrar.
    assert c.post('/api/rows/add',json={'key':'REG-SYNC-DENEGADO','data':{'PROYECTO':'CLARO'}}).status_code==400


def test_sin_modulo_no_sincroniza_aunque_la_sesion_lo_recuerde(app,usuario_modulo,monkeypatch):
    import blueprints.rendicion as flujo
    c,ids,uid=usuario_modulo
    with app.app_context():
        AccesoProyecto.query.filter_by(usuario_id=uid,proyecto_id=ids['Rendicion']).delete()
        db.session.commit()
    def no_descargar(*a,**k):
        pytest.fail('No debe descargar sin acceso al módulo')
    monkeypatch.setattr(flujo.urllib.request,'urlopen',no_descargar)
    assert c.post('/api/rendicion/sync').status_code in (400,403)
    assert c.post('/api/rendicion/sync_sustentos').status_code==403

