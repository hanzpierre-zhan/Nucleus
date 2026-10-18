import json,io
import pytest
from db import db
from models import Proyecto,NucleusData,Usuario,AccesoProyecto

@pytest.fixture
def recursos(app):
    with app.app_context():
        proyectos={p.nombre:p.id for p in Proyecto.query.all()}
        filas=[]
        for proyecto in ('FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO'):
            for catalogo in ('Dataper','Material'):
                key='RECURSO-'+catalogo+'-'+proyecto
                d={'PROYECTO':proyecto,'TECNICO':key,'ESTADO':'ACTIVO','COD_MATERIAL':key,'DESCRIPCION_MATERIAL':key}
                fila=NucleusData(proyecto_id=proyectos[catalogo],key_value=key,data_json=json.dumps(d));db.session.add(fila);filas.append(fila)
        site=NucleusData(proyecto_id=proyectos['SITE'],key_value='SITE-AUTOCOMPLETE',data_json=json.dumps({'Nombre de Site':'SITE AUTOCOMPLETE SIN COORDENADAS'}));db.session.add(site);filas.append(site)
        db.session.commit();ids=[fila.id for fila in filas]
    yield proyectos
    with app.app_context():
        NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False)
        NucleusData.query.filter(NucleusData.key_value=='NUEVO-RECURSO-TEST').delete();db.session.commit()

@pytest.mark.parametrize('nombre',['FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO'])
def test_contexto_filtro_y_nuevo_personal(app,auth_client,recursos,nombre):
    pid=recursos[nombre]
    r=auth_client.get('/flm/%s/recursos/personal'%pid,follow_redirects=True)
    assert r.status_code==200
    assert 'RECURSO-Dataper-'+nombre in r.text
    for otro in ('FLM - ENTEL','FLM - INTEGRATEL','FLM - CLARO'):
        if otro!=nombre: assert 'RECURSO-Dataper-'+otro not in r.text
    assert auth_client.post('/api/rows/add',json={'key':'NUEVO-RECURSO-TEST','data':{'TECNICO':'Nuevo técnico','PROYECTO':'OTRO'}}).status_code==200
    with app.app_context():
        nuevo=NucleusData.query.filter_by(proyecto_id=recursos['Dataper'],key_value='NUEVO-RECURSO-TEST').one()
        assert json.loads(nuevo.data_json)['PROYECTO']==nombre
    otra='FLM - CLARO' if nombre!='FLM - CLARO' else 'FLM - ENTEL'
    key='RECURSO-Dataper-'+otra
    assert auth_client.post('/api/rows/update',json={'key':key,'field':'TECNICO','value':'Alterado'}).status_code==403
    assert auth_client.post('/api/rows/delete',json={'keys':[key]}).status_code==403
    assert auth_client.post('/api/rows/bulk_update',json={'key':'NUEVO-RECURSO-TEST','data':{'PROYECTO':otra}}).status_code==400
    auth_client.get('/switch_project/%s'%pid)
    with auth_client.session_transaction() as ses: assert 'flm_resource_context' not in ses
    meta=auth_client.get('/api/wo/meta').json
    assert any(t['nombre']=='RECURSO-Dataper-'+nombre for t in meta['tecnicos'])
    assert all('RECURSO-Dataper-'+otra!=t['nombre'] for t in meta['tecnicos'])
    assert any(m['descripcion']=='RECURSO-Material-'+nombre for m in meta['materiales'])


def test_sugerencias_y_texto_libre(auth_client,recursos):
    r=auth_client.get('/api/catalogos/autocompletar');assert r.status_code==200
    assert len(r.json['departamentos'])==25 and 'Arequipa' in r.json['departamentos']
    assert 'SITE AUTOCOMPLETE SIN COORDENADAS' in r.json['sites']
    auth_client.get('/switch_project/%s'%recursos['FLM - CLARO'])
    r=auth_client.post('/api/rows/add',json={'key':'NUEVO-RECURSO-TEST','data':{'NOMBRE DE SITE':'SITE NUEVO LIBRE','DEPARTAMENTO':'Arequipa'}})
    assert r.status_code==200,r.json

@pytest.mark.parametrize('recurso',['material','sites','mapa','generadores'])
def test_recursos_disponibles_y_excepciones(auth_client,recursos,recurso):
    assert auth_client.get('/flm/%s/recursos/%s'%(recursos['FLM - CLARO'],recurso),follow_redirects=True).status_code==200
    assert auth_client.get('/flm/%s/recursos/combustible'%recursos['FLM - CLARO']).status_code==404
    assert auth_client.get('/flm/%s/recursos/personal'%recursos['Cotizaciones']).status_code==404


def test_importacion_no_cruza_proyecto(auth_client,recursos):
    auth_client.get('/flm/%s/recursos/personal'%recursos['FLM - CLARO'])
    csv='TECNICO,PROYECTO\nPersona,FLM - ENTEL\n'.encode()
    r=auth_client.post('/api/import/process',data={'file':(io.BytesIO(csv),'personal.csv'),'file_key':'TECNICO','type':'manual_cols'})
    assert r.status_code==400 and 'otro FLM' in r.json['error']


def test_contexto_explicito_no_mezcla_pestanas(app,auth_client,recursos):
    claro=recursos['FLM - CLARO'];entel=recursos['FLM - ENTEL']
    auth_client.get('/flm/%s/recursos/personal'%claro)
    auth_client.get('/flm/%s/recursos/personal'%entel)
    r=auth_client.post('/api/rows/add',headers={'X-FLM-Origin':str(claro),'X-Nucleus-Project':str(recursos['Dataper'])},json={'key':'NUEVO-RECURSO-TEST','data':{'TECNICO':'Técnico de Claro'}})
    assert r.status_code==200,r.json
    with app.app_context():
        fila=NucleusData.query.filter_by(proyecto_id=recursos['Dataper'],key_value='NUEVO-RECURSO-TEST').one()
        assert json.loads(fila.data_json)['PROYECTO']=='FLM - CLARO'


def test_gestor_solo_accede_recursos_de_su_flm(app,client,recursos):
    with app.app_context():
        usuario=Usuario(username='gestor-recursos-test',password_hash='prueba',rol='gestor')
        db.session.add(usuario);db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=usuario.id,proyecto_id=recursos['FLM - CLARO'],restricciones='{}'));db.session.commit();uid=usuario.id
    try:
        with client.session_transaction() as ses:
            ses.update({'user_id':uid,'username':'gestor-recursos-test','rol':'gestor','current_proyecto_id':recursos['FLM - CLARO'],'current_proyecto_nombre':'FLM - CLARO'})
        assert client.get('/flm/%s/recursos/personal'%recursos['FLM - CLARO'],follow_redirects=True).status_code==200
        assert client.get('/flm/%s/recursos/personal'%recursos['FLM - ENTEL']).status_code==403
        assert client.get('/flm/%s/recursos/sites'%recursos['FLM - CLARO'],follow_redirects=True).status_code==200
        assert client.post('/api/rows/add',json={'key':'Prohibido','data':{}}).status_code==403
        assert client.get('/flm/%s/recursos/mapa'%recursos['FLM - CLARO'],follow_redirects=True).status_code==200
        assert client.get('/api/catalogos/autocompletar',headers={'X-FLM-Origin':str(recursos['FLM - ENTEL']),'X-Nucleus-Project':str(recursos['Dataper'])}).status_code==403
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete();Usuario.query.filter_by(id=uid).delete();db.session.commit()


def test_generadores_con_contexto_explicito(auth_client,recursos):
    r=auth_client.get('/flm/%s/recursos/generadores'%recursos['FLM - INTEGRATEL'],follow_redirects=True)
    assert r.status_code==200
    assert '<details class="flm-resource-menu"' not in r.text
    assert '/switch_project/%s?next=/'%recursos['Generadores'] in r.text
    headers={'X-FLM-Origin':str(recursos['FLM - INTEGRATEL']),'X-Nucleus-Project':str(recursos['Generadores'])}
    assert auth_client.get('/api/catalogos/autocompletar',headers=headers).status_code==200
    with auth_client.session_transaction() as ses:
        assert ses['current_proyecto_nombre']=='Generadores'
        assert ses['flm_resource_context']['recurso']=='generadores'

def test_personal_directo_consolida_proyectos_asignados(app,client,recursos):
    with app.app_context():
        usuario=Usuario(username='gestor-consolidado',password_hash='prueba',rol='gestor')
        db.session.add(usuario);db.session.flush();uid=usuario.id
        for nombre in ('FLM - CLARO','FLM - INTEGRATEL'):
            db.session.add(AccesoProyecto(usuario_id=uid,proyecto_id=recursos[nombre],restricciones='{}'))
        db.session.commit()
    try:
        with client.session_transaction() as ses:
            ses.update(user_id=uid,username='gestor-consolidado',rol='gestor',current_proyecto_id=recursos['FLM - CLARO'],current_proyecto_nombre='FLM - CLARO')
        # Even after visiting a per-FLM legacy deep link, the direct module clears that context.
        client.get('/flm/%s/recursos/personal'%recursos['FLM - CLARO'])
        r=client.get('/switch_project/%s?next=/'%recursos['Dataper'],follow_redirects=True)
        assert r.status_code==200
        assert 'RECURSO-Dataper-FLM - CLARO' in r.text
        assert 'RECURSO-Dataper-FLM - INTEGRATEL' in r.text
        assert 'RECURSO-Dataper-FLM - ENTEL' not in r.text
        assert '<details class="flm-resource-menu"' not in r.text
        with client.session_transaction() as ses:
            assert ses['current_proyecto_nombre']=='Dataper' and 'flm_resource_context' not in ses
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete();Usuario.query.filter_by(id=uid).delete();db.session.commit()

def test_personal_nombres_supervisor_y_estado(app,recursos):
    from services.personal import validar,presentar,configurar
    from flask import session
    with app.app_context():
        usuario=Usuario(username='supervisor-personal-prueba',nombre='Supervisora de prueba',password_hash='prueba',rol='supervisor')
        db.session.add(usuario);db.session.flush();uid=usuario.id
        db.session.add(AccesoProyecto(usuario_id=uid,proyecto_id=recursos['FLM - CLARO'],restricciones='{}'));db.session.commit()
    try:
        with app.test_request_context('/'):
            session.update(user_id=uid,rol='supervisor')
            datos=validar({'TECNICO':'Persona nueva','ESTADO':'activo'},nuevo=True)
            assert datos['PROYECTO']=='FLM - CLARO'
            assert datos['SUPERVISOR']=='Supervisora de prueba'
            assert datos['ESTADO']=='ACTIVO'
            assert presentar({'PROYECTO':'INTEGRATEL'})['PROYECTO']=='FLM - INTEGRATEL'
            assert presentar({'PROYECTO':'PEXT'})['PROYECTO']=='FLM - PEXT'
            assert presentar({'PROYECTO':'CLARO'})['SUPERVISOR']==''
            opciones=next(c for c in configurar([]) if c['nombre']=='PROYECTO')['opciones']
            assert opciones==['FLM - CLARO']
            with pytest.raises(ValueError):validar({'PROYECTO':'ENTEL'},nuevo=True)
            with pytest.raises(ValueError):validar({'ESTADO':'CUALQUIERA'})
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete();Usuario.query.filter_by(id=uid).delete();db.session.commit()

@pytest.mark.parametrize('catalogo',['Material','SITE','Generadores'])
def test_proyecto_canonico_en_catalogos(app,auth_client,recursos,catalogo):
    auth_client.get('/switch_project/%s?next=/'%recursos[catalogo])
    r=auth_client.post('/api/rows/add',json={'key':'NUEVO-RECURSO-TEST','data':{'PROYECTO':'CLARO'}})
    assert r.status_code==200,r.text
    with app.app_context():
        fila=NucleusData.query.filter_by(proyecto_id=recursos[catalogo],key_value='NUEVO-RECURSO-TEST').one()
        assert json.loads(fila.data_json)['PROYECTO']=='FLM - CLARO'
    r=auth_client.post('/api/rows/bulk_update',json={'key':'NUEVO-RECURSO-TEST','data':{'PROYECTO':'PEXT'}})
    assert r.status_code==200,r.text
    with app.app_context():
        db.session.expire_all()
        fila=NucleusData.query.filter_by(proyecto_id=recursos[catalogo],key_value='NUEVO-RECURSO-TEST').one()
        assert json.loads(fila.data_json)['PROYECTO']=='FLM - PEXT'
    r=auth_client.post('/api/rows/update',json={'key':'NUEVO-RECURSO-TEST','field':'PROYECTO','value':'DESCONOCIDO'})
    assert r.status_code==400
    html=auth_client.get('/').text
    assert 'FLM - INTEGRATEL' in html and '"PROYECTO"' in html


def test_catalogo_no_asigna_proyecto_a_historicos():
    from services.proyectos_catalogo import presentar
    original={'CODIGO':'HISTORICO'}
    assert presentar(original)['PROYECTO']==''
    assert 'PROYECTO' not in original


@pytest.mark.parametrize('rol', ['gestor', 'supervisor'])
def test_personal_diez_claro_mas_diez_integratel(app, client, rol):
    """Caso solicitado: dos proyectos se consolidan sin incluir un tercero."""
    with app.app_context():
        ids = {p.nombre: p.id for p in Proyecto.query.all()}
        usuario = Usuario(username='revision-pepito-'+rol, password_hash='sin-login', rol=rol)
        db.session.add(usuario); db.session.flush(); uid = usuario.id
        for nombre in ('Dataper', 'FLM - CLARO', 'FLM - INTEGRATEL'):
            db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=ids[nombre], restricciones='{}'))
        filas = []
        for proyecto, cantidad in [('FLM - CLARO',10),('FLM - INTEGRATEL',10),('FLM - ENTEL',1)]:
            for i in range(cantidad):
                clave='REVISION-PEPITO-'+rol+'-'+proyecto+'-'+str(i)
                fila=NucleusData(proyecto_id=ids['Dataper'],key_value=clave,data_json=json.dumps({'DOCUMENTO':clave,'TECNICO':clave,'PROYECTO':proyecto,'ESTADO':'ACTIVO'}))
                db.session.add(fila);filas.append(fila)
        db.session.commit(); creados=[f.id for f in filas]
    try:
        with client.session_transaction() as ses:
            ses.update(user_id=uid,username='revision-pepito-'+rol,rol=rol)
        respuesta=client.get('/switch_project/%s?next=/'%ids['Dataper'],follow_redirects=True)
        assert respuesta.status_code==200
        for proyecto in ('FLM - CLARO','FLM - INTEGRATEL'):
            for i in range(10):assert 'REVISION-PEPITO-'+rol+'-'+proyecto+'-'+str(i) in respuesta.text
        assert 'REVISION-PEPITO-'+rol+'-FLM - ENTEL-0' not in respuesta.text
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid,proyecto_id=ids['FLM - CLARO']).delete();db.session.commit()
        respuesta=client.get('/')
        assert 'REVISION-PEPITO-'+rol+'-FLM - CLARO-0' not in respuesta.text
        assert 'REVISION-PEPITO-'+rol+'-FLM - INTEGRATEL-0' in respuesta.text
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete()
            NucleusData.query.filter(NucleusData.id.in_(creados)).delete(synchronize_session=False)
            Usuario.query.filter_by(id=uid).delete();db.session.commit()
