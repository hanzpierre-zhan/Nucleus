"""Pruebas de correlación entre módulos con datos ficticios y base temporal."""
import json
import pytest
from db import db
from models import Proyecto,NucleusData,RefacturableDetalle,LiquidacionNumero,Usuario,AccesoProyecto


@pytest.mark.parametrize('negocio,cliente', [('FLM - ENTEL','ENTEL'),('FLM - INTEGRATEL','INTEGRATEL'),('FLM - CLARO','CLARO'),('FLM - PEXT','PEXT')])
def test_catalogos_wo_cotizacion_liquidacion_rendicion(app,auth_client,negocio,cliente):
    sufijo=cliente;person='CADENA-PERSONAL-'+sufijo;material='CADENA-MATERIAL-'+sufijo;wo='CADENA-WO-'+sufijo;cot='CADENA-COT-'+sufijo
    creados=[]
    with app.app_context():ids={p.nombre:p.id for p in Proyecto.query.all()}
    def crear(modulo,key,datos):
        auth_client.get('/switch_project/%s?next=/'%ids[modulo])
        r=auth_client.post('/api/rows/add',json={'key':key,'data':datos});assert r.status_code==200,r.json
        with app.app_context():
            f=NucleusData.query.filter_by(proyecto_id=ids[modulo],key_value=r.json.get('key',key)).one();creados.append(f.id)
        return r.json.get('key',key)
    try:
        crear('Dataper',person,{'PROYECTO':negocio,'TECNICO':person,'ESTADO':'ACTIVO'})
        crear('Material',material,{'PROYECTO':negocio,'DESCRIPCION_MATERIAL':material,'UM':'UND'})
        auth_client.get('/switch_project/%s?next=/'%ids[negocio]);meta=auth_client.get('/api/wo/meta').json
        assert person in {x['nombre'] for x in meta['tecnicos']}
        assert material in {x['descripcion'] for x in meta['materiales']}
        crear(negocio,wo,{'_BITACORA_INICIO':'Origen A'})
        with app.app_context():
            c=NucleusData(proyecto_id=ids['Cotizaciones'],key_value=cot,data_json=json.dumps({'CLIENTE':cliente,'ESTADO COTIZACION':'Aprobado','NUMERO WO':wo,'SUB TOTAL + FEE':'100.00'}))
            r=NucleusData(proyecto_id=ids['Rendicion'],key_value='CADENA-REND-'+sufijo,data_json=json.dumps({'Nombre del proyecto':cliente,'Número CM / PM / PLM':wo,'ESTADO':'VALIDADO','Monto total del depósito':'100'}))
            db.session.add_all([c,r]);db.session.commit();cid=c.id;creados.extend([c.id,r.id])
        auth_client.get('/switch_project/%s?next=/'%ids['Cotizaciones'])
        sustento=auth_client.get('/api/cotizacion/sustento',query_string={'key':cot});assert sustento.status_code==200,sustento.json
        assert sustento.json['wos'][0]['wo_data']['_BITACORA_INICIO']=='Origen A'
        auth_client.get('/switch_project/%s?next=/'%ids[negocio])
        cambio=auth_client.post('/api/rows/bulk_update',json={'key':wo,'data':{'_BITACORA_INICIO':'Actualizado B'}});assert cambio.status_code==200,cambio.json
        sustento=auth_client.get('/api/cotizacion/sustento',query_string={'key':cot})
        assert sustento.json['wos'][0]['wo_data']['_BITACORA_INICIO']=='Actualizado B'
        rend=auth_client.get('/api/rendicion/por_wo',query_string={'key':wo,'proyecto_id':ids[negocio]})
        assert rend.status_code==200,rend.json
        assert len(rend.json['lista'])==1 and rend.json['lista'][0]['estado']=='VALIDADO'
        cobro=auth_client.patch('/refacturable/api/registros/%s'%cid,json={'monto_cobra':'150.00'})
        assert cobro.status_code==200,cobro.json
        assert cobro.json['registro']['margen']=='50.00'
        assert any(f['id']==cid for f in auth_client.get('/refacturable/api/registros').json['registros'])
    finally:
        with app.app_context():
            RefacturableDetalle.query.filter(RefacturableDetalle.origen_id.in_(creados)).delete(synchronize_session=False)
            LiquidacionNumero.query.filter(LiquidacionNumero.origen_id.in_(creados)).delete(synchronize_session=False)
            NucleusData.query.filter(NucleusData.id.in_(creados)).delete(synchronize_session=False);db.session.commit()


def test_combustible_por_wo_no_expone_otro_proyecto(app,client):
    filas=[]
    with app.app_context():
        ids={p.nombre:p.id for p in Proyecto.query.all()}
        u=Usuario(username='auditor-gestor-local',password_hash='sin-login',rol='gestor');db.session.add(u);db.session.flush();uid=u.id
        db.session.add(AccesoProyecto(usuario_id=uid,proyecto_id=ids['FLM - CLARO'],restricciones='{}'))
        db.session.add(AccesoProyecto(usuario_id=uid,proyecto_id=ids['Combustible'],restricciones='{}'))
        for n,negocio in [('PROPIA','FLM - CLARO'),('AJENA','FLM - ENTEL')]:
            f=NucleusData(proyecto_id=ids[negocio],key_value='AUD-COMB-'+n,data_json='{}');db.session.add(f);filas.append(f)
            f=NucleusData(proyecto_id=ids['Combustible'],key_value='AUD-MOV-'+n,data_json=json.dumps({'WO NUMBER':'AUD-COMB-'+n,'GALONES':'10'}));db.session.add(f);filas.append(f)
        db.session.commit();rids=[f.id for f in filas]
    try:
        with client.session_transaction() as s:s.update(user_id=uid,username='auditor-gestor-local',rol='gestor')
        propia=client.get('/api/combustible/por_wo?wo=AUD-COMB-PROPIA');assert propia.status_code==200 and len(propia.json['movimientos'])==1
        ajena=client.get('/api/combustible/por_wo?wo=AUD-COMB-AJENA');assert ajena.status_code==403 and 'movimientos' not in ajena.json
        assert client.get('/api/combustible/por_wo?wo=NO-EXISTE').status_code==403
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid,proyecto_id=ids['Combustible']).delete();db.session.commit()
        assert client.get('/api/combustible/por_wo?wo=AUD-COMB-PROPIA').status_code==403
    finally:
        with app.app_context():
            AccesoProyecto.query.filter_by(usuario_id=uid).delete();NucleusData.query.filter(NucleusData.id.in_(rids)).delete(synchronize_session=False);Usuario.query.filter_by(id=uid).delete();db.session.commit()

def test_duplicar_usuario_conserva_proyectos_modulos_sin_compartir_perfil(app,auth_client):
    from models import CuentaEspacio,AccesoEspacio,PerfilEspacio
    uids=[];pids=[]
    with app.app_context():
        proyecto=Proyecto.query.filter_by(nombre='FLM - CLARO').one().id
        u=Usuario(username='auditoria-clonar-origen',password_hash='no-login',rol='gestor')
        perfil=PerfilEspacio(nombre='Auditoría clonar origen',permisos_json=json.dumps({'rendicion':['consultar']}))
        db.session.add_all([u,perfil]);db.session.flush();uid,pid=u.id,perfil.id;uids.append(uid);pids.append(pid)
        db.session.add(CuentaEspacio(usuario_id=uid));db.session.add(AccesoEspacio(usuario_id=uid,proyecto_id=proyecto,perfil_id=pid));db.session.commit()
    try:
        r=auth_client.post('/api/admin/usuario/duplicar',json={'source_id':uid,'new_username':'auditoria-clonar-destino','new_password':'solo-fixture-local'})
        assert r.status_code==200,r.json
        copia=r.json['id'];uids.append(copia)
        with app.app_context():
            assert db.session.get(CuentaEspacio,copia) is not None
            acceso=AccesoEspacio.query.filter_by(usuario_id=copia).one();pids.append(acceso.perfil_id)
            assert acceso.proyecto_id==proyecto and acceso.perfil_id!=pid
            assert json.loads(db.session.get(PerfilEspacio,acceso.perfil_id).permisos_json)=={'rendicion':['consultar']}
            db.session.get(PerfilEspacio,pid).permisos_json='{}';db.session.commit()
            assert json.loads(db.session.get(PerfilEspacio,acceso.perfil_id).permisos_json)=={'rendicion':['consultar']}
    finally:
        with app.app_context():
            AccesoEspacio.query.filter(AccesoEspacio.usuario_id.in_(uids)).delete(synchronize_session=False)
            CuentaEspacio.query.filter(CuentaEspacio.usuario_id.in_(uids)).delete(synchronize_session=False)
            PerfilEspacio.query.filter(PerfilEspacio.id.in_(pids)).delete(synchronize_session=False)
            AccesoProyecto.query.filter(AccesoProyecto.usuario_id.in_(uids)).delete(synchronize_session=False)
            Usuario.query.filter(Usuario.id.in_(uids)).delete(synchronize_session=False);db.session.commit()


def test_soporte_no_duplica_zeno(app,auth_client):
    with app.app_context():uid=Usuario.query.filter_by(username='zeno').one().id
    with auth_client.session_transaction() as s:s['rol']='suport'
    r=auth_client.post('/api/admin/usuario/duplicar',json={'source_id':uid,'new_username':'NO-DEBE-CREARSE','new_password':'solo-fixture-local'})
    assert r.status_code==403
    with app.app_context():assert Usuario.query.filter_by(username='NO-DEBE-CREARSE').first() is None
