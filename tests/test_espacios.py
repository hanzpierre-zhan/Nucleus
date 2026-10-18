import json

import pytest
from db import db
from models import (Proyecto, Usuario, NucleusData, PerfilEspacio, AccesoEspacio,
                    CuentaEspacio, ClasificacionEspacio, AuditoriaEspacio, HistorialCambios,
                    ProyectoNegocio)


@pytest.fixture
def piloto(app, client, monkeypatch):
    monkeypatch.setitem(app.config, 'ESPACIOS_HABILITADOS', True)
    with app.app_context():
        proyectos = {p.nombre: p.id for p in Proyecto.query.all()}
        usuario = Usuario(username='gestor-espacios', password_hash='no-login', rol='gestor')
        db.session.add(usuario)
        perfil = PerfilEspacio(nombre='Prueba gestor', permisos_json=json.dumps({
            'personal': ['consultar', 'exportar', 'editar'], 'rendicion': ['consultar', 'validar'],
            'operacion': ['consultar'], 'combustible': ['consultar']}))
        db.session.add(perfil); db.session.flush()
        uid, perfil_id = usuario.id, perfil.id
        db.session.add(CuentaEspacio(usuario_id=uid))
        db.session.add(AccesoEspacio(usuario_id=uid, proyecto_id=proyectos['FLM - CLARO'], perfil_id=perfil_id))
        filas = []
        for nombre in ('Claro', 'Entel', 'Entel - Pext', 'Integratel'):
            f = NucleusData(proyecto_id=proyectos['Dataper'], key_value='PILOTO-' + nombre,
                            data_json=json.dumps({'PROYECTO': nombre, 'TECNICO': nombre, 'ESTADO': 'ACTIVO'}))
            db.session.add(f); filas.append(f)
        for fecha in ('9/10/2026 12:00:00', '17/10/2026 08:00:00', '30/9/2026 15:00:00'):
            f = NucleusData(proyecto_id=proyectos['Rendicion'], key_value='PILOTO-' + fecha,
                            data_json=json.dumps({'Nombre del proyecto':'Claro','Marca temporal':fecha,'ESTADO':'PENDIENTE','TIPO DE PRESUPUESTO':'NO REFACTURABLE'}))
            db.session.add(f); filas.append(f)
        f = NucleusData(proyecto_id=proyectos['Dataper'],key_value='PILOTO-AMBIGUO',data_json=json.dumps({'TECNICO':'Sin atribución'}))
        db.session.add(f); filas.append(f)
        # WO repetida entre dos proyectos: no adivinar a quién pertenece el gasto.
        for nombre in ('FLM - CLARO','FLM - ENTEL'):
            f = NucleusData(proyecto_id=proyectos[nombre],key_value='PILOTO-WO',data_json='{}')
            db.session.add(f); filas.append(f)
        f = NucleusData(proyecto_id=proyectos['Combustible'],key_value='PILOTO-GASTO',data_json=json.dumps({'WO NUMBER':'PILOTO-WO'}))
        db.session.add(f); filas.append(f)
        db.session.commit()
        ids = [f.id for f in filas]
        nombres = {f.key_value: f.id for f in filas}
    with client.session_transaction() as s:
        s.update(user_id=uid, username='gestor-espacios', rol='gestor', espacios_csrf='prueba-csrf')
    yield {'ids': proyectos, 'registros': nombres, 'uid': uid, 'perfil_id': perfil_id, 'cliente':client}
    with app.app_context():
        AuditoriaEspacio.query.filter_by(usuario_id=uid).delete()
        HistorialCambios.query.filter_by(usuario_id=uid).delete()
        ClasificacionEspacio.query.filter(ClasificacionEspacio.registro_id.in_(ids)).delete(synchronize_session=False)
        AccesoEspacio.query.filter_by(usuario_id=uid).delete()
        CuentaEspacio.query.filter_by(usuario_id=uid).delete()
        NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False)
        PerfilEspacio.query.filter_by(id=perfil_id).delete()
        Usuario.query.filter_by(id=uid).delete(); db.session.commit()


def test_gestor_solo_ve_su_universo_y_no_puede_adivinar_ids(piloto):
    c = piloto['cliente']
    j = c.get('/api/espacios/personal/registros').json
    assert {f['clave'] for f in j['registros']} == {'PILOTO-Claro'}
    assert c.get('/api/espacios/personal/registros?proyecto=%s' % piloto['ids']['FLM - ENTEL']).status_code == 403
    otro = piloto['registros']['PILOTO-Entel']
    assert c.get('/api/espacios/personal/registros/%s' % otro).status_code == 404
    assert c.get('/api/espacios/cotizaciones/registros').status_code == 403
    assert c.get('/api/espacios/administracion').status_code == 403
    assert c.get('/api/espacios/pendientes').status_code == 403


def test_exportacion_y_fecha_descendente(piloto):
    c = piloto['cliente']
    csv = c.get('/api/espacios/personal/exportar').text
    assert 'PILOTO-Claro' in csv and 'PILOTO-Entel' not in csv
    assert c.get('/api/espacios/rendicion/exportar').status_code == 403
    fechas = [f['datos']['Marca temporal'] for f in c.get('/api/espacios/rendicion/registros').json['registros']]
    assert fechas == ['17/10/2026 08:00:00','9/10/2026 12:00:00','30/9/2026 15:00:00']


def test_revocar_no_reabre_rutas_anteriores(app,piloto):
    c = piloto['cliente']
    assert c.get('/').status_code == 302
    assert c.get('/api/wo/meta').status_code == 403
    assert c.post('/api/rows/update',json={'key':'PILOTO-Entel','field':'TECNICO','value':'ataque'}).status_code == 403
    with app.app_context():
        AccesoEspacio.query.filter_by(usuario_id=piloto['uid']).delete();db.session.commit()
    assert c.get('/api/espacios/personal/registros').status_code == 403
    assert c.get('/api/wo/meta').status_code == 403


def test_entel_y_pext_son_espacios_distintos(app,piloto):
    c = piloto['cliente']
    with app.app_context():
        a = AccesoEspacio.query.filter_by(usuario_id=piloto['uid']).one()
        a.proyecto_id = piloto['ids']['FLM - ENTEL'];db.session.commit()
    assert {f['clave'] for f in c.get('/api/espacios/personal/registros').json['registros']} == {'PILOTO-Entel'}


def test_consolidado_solo_de_los_proyectos_asignados(app,piloto):
    with app.app_context():
        db.session.add(AccesoEspacio(usuario_id=piloto['uid'],proyecto_id=piloto['ids']['FLM - INTEGRATEL'],perfil_id=piloto['perfil_id']));db.session.commit()
    c = piloto['cliente']
    assert {f['proyecto'] for f in c.get('/api/espacios/personal/registros').json['registros']} == {'Claro','Integratel'}
    claro = piloto['ids']['FLM - CLARO']
    assert {f['proyecto'] for f in c.get('/api/espacios/personal/registros?proyecto=%s' % claro).json['registros']} == {'Claro'}


def test_cruce_ambiguo_no_se_expone(piloto):
    assert piloto['cliente'].get('/api/espacios/combustible/registros').json['registros'] == []


def test_edicion_valida_version_y_pertenencia(piloto):
    c = piloto['cliente']; rid = piloto['registros']['PILOTO-Claro']
    url = '/api/espacios/personal/registros/%s' % rid
    detalle = c.get(url).json
    datos = {'key':'PILOTO-Claro','field':'TECNICO','value':'Nuevo nombre','revision':detalle['revision']}
    assert c.patch(url,json=datos).status_code == 403  # sin CSRF
    headers = {'X-Espacios-CSRF':'prueba-csrf'}
    assert c.patch(url,json={**datos,'field':'PROYECTO','value':'Entel'},headers=headers).status_code == 400
    assert c.patch(url,json={**datos,'revision':'obsoleta'},headers=headers).status_code == 409
    r = c.patch(url,json=datos,headers=headers)
    assert r.status_code == 200, r.json
    assert c.get(url).json['datos']['TECNICO'] == 'Nuevo nombre'


def test_permisos_revocados_se_aplican_sin_reiniciar_sesion(app,piloto):
    c = piloto['cliente']
    assert c.get('/api/espacios/personal/registros').status_code == 200
    with app.app_context():
        p = db.session.get(PerfilEspacio,piloto['perfil_id']);p.permisos_json='{}';db.session.commit()
    assert c.get('/api/espacios/personal/registros').status_code == 403


def test_piloto_desactivado_no_expone_rutas(app,auth_client,monkeypatch):
    monkeypatch.setitem(app.config,'ESPACIOS_HABILITADOS',False)
    assert auth_client.get('/espacios').status_code == 404


def test_admin_clasifica_sin_mover_registro(app,auth_client,piloto):
    auth_client.get('/espacios')
    with auth_client.session_transaction() as s: token = s['espacios_csrf']
    rid = piloto['registros']['PILOTO-AMBIGUO']; pid = piloto['ids']['FLM - CLARO']
    r = auth_client.post('/api/espacios/clasificaciones',headers={'X-Espacios-CSRF':token},json={'registro_id':rid,'proyecto_id':pid,'motivo':'Revisión documental'})
    assert r.status_code == 200
    assert 'PILOTO-AMBIGUO' in {f['clave'] for f in piloto['cliente'].get('/api/espacios/personal/registros').json['registros']}
    with app.app_context():
        assert db.session.get(NucleusData,rid).proyecto_id == piloto['ids']['Dataper']


def test_gestor_accion_solo_en_su_proyecto(app,piloto,monkeypatch):
    import blueprints.rendicion as rend
    monkeypatch.setattr(rend,'_avisar_flujo',lambda *a:None)
    c = piloto['cliente']; clave = 'PILOTO-17/10/2026 08:00:00'; rid = piloto['registros'][clave]
    url = '/api/espacios/rendicion/registros/%s/accion' % rid
    headers = {'X-Espacios-CSRF':'prueba-csrf'}
    monkeypatch.setattr('services.rendicion_validadores.puede_validar',lambda *a:False)
    r = c.post(url,headers=headers,json={'key':clave,'accion':'validar','tiempo':'No aplica'})
    assert r.status_code == 403  # El perfil no salta los validadores del flujo.
    assert c.post(url,headers=headers,json={'key':clave,'accion':'depositar'}).status_code == 404


def test_flujo_desde_espacio_hasta_cierre_con_importacion(app,auth_client,piloto,monkeypatch):
    import io
    import blueprints.rendicion as rend
    import blueprints.admin as admin
    monkeypatch.setattr(rend,'_avisar_flujo',lambda *a:None)
    monkeypatch.setattr(rend,'_persistir_fotos_form',lambda *a:None)
    monkeypatch.setattr('services.rendicion_validadores.puede_validar',lambda *a:True)
    with app.app_context():
        perfil = db.session.get(PerfilEspacio,piloto['perfil_id'])
        perfil.permisos_json=json.dumps({'rendicion':['consultar','validar','depositar','sustentar','archivar']})
        db.session.commit()
    c = piloto['cliente']; clave = 'PILOTO-17/10/2026 08:00:00';rid = piloto['registros'][clave]
    url = '/api/espacios/rendicion/registros/%s/accion' % rid
    headers = {'X-Espacios-CSRF':'prueba-csrf'}
    for accion,campos,estado in [('validar',{'tiempo':'No aplica'},'VALIDADO'),
        ('depositar',{'fecha_pago':'2026-10-17','monto_pago':'100','foto_pago':'/static/prueba.jpg'},'DEPOSITADO')]:
        r=c.post(url,headers=headers,json={'key':clave,'accion':accion,**campos})
        assert r.status_code==200,r.json
        assert r.json['newData']['ESTADO']==estado
    with app.app_context():
        datos=json.loads(db.session.get(NucleusData,rid).data_json)
        codigo=datos['CODIGO DEPOSITO']
    csv=('Marca temporal,Codigo deposito,Comentario\nENVIO-PILOTO,'+codigo+',Comprobante\n').encode()
    monkeypatch.setattr(admin.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(csv))
    r=auth_client.post('/api/rendicion/sync_sustentos')
    assert r.status_code==200 and r.json['actualizados']==1,r.json
    for accion,estado in [('sustentar','SUSTENTADO'),('archivar','ARCHIVADO')]:
        r=c.post(url,headers=headers,json={'key':clave,'accion':accion,'comentario':'Verificado'})
        assert r.status_code==200,r.json
        assert r.json['newData']['ESTADO']==estado
    with app.app_context():
        final=json.loads(db.session.get(NucleusData,rid).data_json)
        assert final['SUSTENTO_COMENTARIO']=='Comprobante'
        from decimal import Decimal
        assert Decimal(final['MONTO PAGO']) == Decimal('100.00')


def test_agregar_proyecto_no_otorga_acceso_automatico(app,auth_client,piloto):
    auth_client.get('/espacios')
    with auth_client.session_transaction() as s:token=s['espacios_csrf']
    headers={'X-Espacios-CSRF':token}
    r=auth_client.post('/api/espacios/proyectos',headers=headers,json={'nombre':'Proyecto futuro de prueba'})
    assert r.status_code==200,r.json
    pid=r.json['id']
    try:
        assert pid in {p['id'] for p in auth_client.get('/api/espacios/contexto').json['proyectos']}
        assert pid not in {p['id'] for p in piloto['cliente'].get('/api/espacios/contexto').json['proyectos']}
        assert piloto['cliente'].get('/api/espacios/personal/registros?proyecto=%s'%pid).status_code==403
        with app.test_request_context():
            from services.espacios import nombre_negocio
            assert nombre_negocio('Proyecto futuro de prueba')=='FLM - PROYECTO FUTURO DE PRUEBA'
    finally:
        with app.app_context():
            ProyectoNegocio.query.filter_by(proyecto_id=pid).delete()
            Proyecto.query.filter_by(id=pid).delete();db.session.commit()


def test_perfiles_administrables_validan_acciones_y_csrf(app,auth_client,piloto):
    auth_client.get('/espacios')
    with auth_client.session_transaction() as s:token=s['espacios_csrf']
    headers={'X-Espacios-CSRF':token}
    url='/api/espacios/perfiles'
    assert auth_client.post(url,json={'nombre':'Perfil inválido','permisos':{}}).status_code==403
    assert auth_client.post(url,headers=headers,json={'nombre':'Perfil inválido','permisos':{'personal':['depositar']}}).status_code==400
    r=auth_client.post(url,headers=headers,json={'nombre':'Certificador de ensayo','permisos':{'liquidaciones':['consultar','exportar']}})
    assert r.status_code==200,r.json
    try:
        r=auth_client.post('/api/espacios/asignaciones',headers=headers,json={'usuario_id':piloto['uid'],
            'proyecto_id':piloto['ids']['FLM - INTEGRATEL'],'perfil_id':r.json['id']})
        assert r.status_code==200,r.json
        c=piloto['cliente']
        assert c.get('/api/espacios/liquidaciones/registros').status_code==200
        assert c.get('/api/espacios/personal/registros?proyecto=%s'%piloto['ids']['FLM - INTEGRATEL']).status_code==403
    finally:
        with app.app_context():
            perfil=PerfilEspacio.query.filter_by(nombre='Certificador de ensayo').one()
            AccesoEspacio.query.filter_by(perfil_id=perfil.id).delete()
            db.session.delete(perfil);db.session.commit()

def test_menu_separa_proyectos_modulos_y_configuracion(piloto):
    r = piloto['cliente'].get('/espacios?modulo=rendicion')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Proyectos</div>' in html and 'Módulos</div>' in html
    assert 'FLM - CLARO' in html
    assert 'FLM - INTEGRATEL' not in html
    assert 'href="/usuarios"' not in html
    assert 'Espacios por proyecto</span>' not in html


def test_selector_depende_del_modulo_no_del_total_de_asignaciones(app,piloto):
    with app.app_context():
        perfil=PerfilEspacio(nombre='Solo combustible temporal',permisos_json=json.dumps({'combustible':['consultar']}))
        db.session.add(perfil);db.session.flush()
        acceso=AccesoEspacio(usuario_id=piloto['uid'],proyecto_id=piloto['ids']['FLM - ENTEL'],perfil_id=perfil.id)
        db.session.add(acceso);db.session.commit()
        aid,pid=acceso.id,perfil.id
    try:
        html=piloto['cliente'].get('/espacios?modulo=rendicion').text
        assert 'FLM - ENTEL' not in html
        assert 'FLM - CLARO' in html
        html=piloto['cliente'].get('/espacios?modulo=combustible').text
        assert 'FLM - ENTEL' in html and 'Todos mis proyectos' in html
    finally:
        with app.app_context():
            db.session.delete(db.session.get(AccesoEspacio,aid));db.session.delete(db.session.get(PerfilEspacio,pid));db.session.commit()


def test_mapa_filtra_puntos_por_proyecto_y_valida_coordenadas(app,piloto):
    with app.app_context():
        perfil=db.session.get(PerfilEspacio,piloto['perfil_id'])
        permisos=json.loads(perfil.permisos_json);permisos['mapa_sites']=['consultar'];perfil.permisos_json=json.dumps(permisos)
        filas=[]
        for proyecto,lat in [('Claro','-12.1'),('Entel','-11.2'),('Claro','NaN')]:
            f=NucleusData(proyecto_id=piloto['ids']['SITE'],key_value='MAPA-PRUEBA-'+proyecto+lat,data_json=json.dumps({'PROYECTO':proyecto,'LATITUD':lat,'LONGITUD':'-77.1'}))
            db.session.add(f);filas.append(f)
        db.session.commit();ids=[f.id for f in filas]
    try:
        j=piloto['cliente'].get('/api/espacios/mapa_sites/mapa').json
        assert len(j['puntos'])==1 and j['puntos'][0]['proyecto']=='Claro'
        assert j['sin_coordenadas']==1
        assert piloto['cliente'].get('/api/espacios/mapa_sites/mapa?proyecto='+str(piloto['ids']['FLM - ENTEL'])).status_code==403
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()

def test_rendicion_cuatro_proyectos_y_vista_individual(app,piloto):
    with app.app_context():
        for nombre in ('FLM - ENTEL','FLM - INTEGRATEL','FLM - PEXT'):
            db.session.add(AccesoEspacio(usuario_id=piloto['uid'],proyecto_id=piloto['ids'][nombre],perfil_id=piloto['perfil_id']))
        filas=[]
        for proyecto in ('Entel','Integratel','Entel - Pext'):
            f=NucleusData(proyecto_id=piloto['ids']['Rendicion'],key_value='REND-ALCANCE-'+proyecto,data_json=json.dumps({'Nombre del proyecto':proyecto,'ESTADO':'PENDIENTE'}))
            db.session.add(f);filas.append(f)
        db.session.commit();ids=[f.id for f in filas]
    try:
        c=piloto['cliente']
        assert {f['proyecto'] for f in c.get('/api/espacios/rendicion/registros').json['registros']} == {'Claro','Entel','Integratel','Entel - Pext'}
        pext=piloto['ids']['FLM - PEXT']
        assert {f['proyecto'] for f in c.get('/api/espacios/rendicion/registros?proyecto='+str(pext)).json['registros']} == {'Entel - Pext'}
        html=c.get('/espacios?modulo=rendicion').text
        assert all(n in html for n in ('FLM - ENTEL','FLM - CLARO','FLM - INTEGRATEL','FLM - PEXT','Todos mis proyectos'))
    finally:
        with app.app_context():
            NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()

def test_usuario_guarda_proyectos_y_modulos_en_una_operacion(app,auth_client,piloto):
    auth_client.get('/usuarios')
    with auth_client.session_transaction() as s: token=s['espacios_csrf']
    headers={'X-Espacios-CSRF':token}
    payload={'id':piloto['uid'],'username':'gestor-espacios','nombre':'Prueba','rol':'gestor',
             'proyectos':[piloto['ids']['FLM - CLARO'],piloto['ids']['FLM - ENTEL']],
             'modulos':['rendicion']}
    try:
        r=auth_client.put('/api/espacios/usuarios',headers=headers,json=payload)
        assert r.status_code==200, r.text
        c=piloto['cliente']
        assert c.get('/api/espacios/personal/registros').status_code==403
        assert c.get('/api/espacios/rendicion/registros?proyecto='+str(piloto['ids']['FLM - ENTEL'])).status_code==200
        assert c.get('/api/espacios/rendicion/registros?proyecto='+str(piloto['ids']['FLM - PEXT'])).status_code==403
        assert auth_client.get('/espacios?administrar=1').headers['Location']=='/usuarios'
        html=auth_client.get('/usuarios').text
        assert 'class="negocio-check"' in html and 'class="modulo-check"' in html
        assert 'Perfiles y permisos</a>' not in html
        # An invalid update must leave both account data and scope unchanged.
        invalido={**payload,'nombre':'No guardar','proyectos':[9999999]}
        assert auth_client.put('/api/espacios/usuarios',headers=headers,json=invalido).status_code==400
        with app.app_context():assert db.session.get(Usuario,piloto['uid']).nombre=='Prueba'
    finally:
        with app.app_context():
            AccesoEspacio.query.filter_by(usuario_id=piloto['uid']).delete()
            PerfilEspacio.query.filter_by(nombre='Cuenta · '+str(piloto['uid'])).delete()
            db.session.commit()


def test_usuario_integrado_deniega_modulos_o_proyectos_vacios(app,auth_client,piloto):
    auth_client.get('/usuarios')
    with auth_client.session_transaction() as s:token=s['espacios_csrf']
    payload={'id':piloto['uid'],'username':'gestor-espacios','rol':'gestor','proyectos':[],'modulos':['rendicion']}
    assert auth_client.put('/api/espacios/usuarios',headers={'X-Espacios-CSRF':token},json=payload).status_code==400
    assert auth_client.put('/api/espacios/usuarios',json=payload).status_code==403

def test_admin_abre_modulos_originales_sin_tabla_generica(app,auth_client,piloto):
    for modulo,nombre in [('operacion','FLM - ENTEL'),('combustible','Combustible'),('cotizaciones','Cotizaciones'),('rendicion','Rendicion')]:
        r=auth_client.get('/espacios?modulo='+modulo)
        assert r.status_code==302
        assert r.headers['Location']=='/switch_project/%s?next=/'%piloto['ids'][nombre]
    html=auth_client.get('/usuarios').text
    assert '/switch_project/%s?next=/'%piloto['ids']['FLM - ENTEL'] in html
    assert 'Espacios por proyecto</span>' not in html
    assert 'class="sidebar-link-text">Operación FLM</span>' not in html
    assert 'class="negocio-check"' in html and 'class="modulo-check"' in html
