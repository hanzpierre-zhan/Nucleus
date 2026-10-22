from datetime import date
from services.dashboard_integratel import indicadores


def test_produccion_por_creacion_y_backlog_solo_meses_anteriores():
    rows = [
        {'_key':'CM-1','OPERATE PHASE':' close ', 'FECHA DE CREACIÓN':'2026-09-30 20:00', 'DEPARTAMENTO':'LIMA','NOMBRE DE SITE':'A'},
        {'_key':'PM-2','OPERATE PHASE':'complete','FECHA DE CREACION':'2026-09-30'},
        {'_key':'PLM-3','OPERATE PHASE':'arrive','FECHA DE CREACION':'01/10/2026'},
        {'_key':'CM-4','OPERATE PHASE':'leave','FECHA DE CREACION':'2025-12-01'},
        {'_key':'CM-5','OPERATE PHASE':'close','FECHA DE CREACION':'2026-10-01','DEPARTAMENTO':'LIMA','NOMBRE DE SITE':'A'},
        {'_key':'PM-6','OPERATE PHASE':'dispatch'},
        {'_key':'PLM-7','OPERATE PHASE':'accept','FECHA DE CREACION':'2026-11-01'},
    ]
    result = indicadores(rows, date(2026,10,13))
    assert result['produccion'] == 2
    assert result['meses'] == {'2026-09':1,'2026-10':1}
    assert result['backlog'] == 2
    assert result['en_atencion'] == 1
    assert result['sin_fecha'] == 1 and result['futuros'] == 1
    assert result['departamentos'] == [('LIMA',2)]
    assert result['sites'] == [('A',2)]
    assert result['tipos']['Backlog'] == {'PM':1,'CM':1}
    assert result['tipos']['En atención'] == {'PLM':1}


def test_cambio_de_anio_y_close_sin_fecha_no_inventa_un_mes():
    result = indicadores([
        {'_key':'CM-1','OPERATE PHASE':'depart','FECHA DE CREACION':'2026-12-31'},
        {'_key':'PM-2','OPERATE PHASE':'close','FECHA DE CREACION':'incorrecta'},
        {'_key':'PLM-3','OPERATE PHASE':'complete','FECHA DE CREACION':'2027-01-01'},
    ], date(2027,1,1))
    assert result['backlog'] == 1 and result['en_atencion'] == 1
    assert result['produccion'] == 1 and result['meses'] == {}


def test_columnas_reales_integratel_y_departamento_duplicado_vacio():
    result=indicadores([{'Número de WO':'PLM-99','Operate Phase':'close',
                        'Fecha de creación (WO Creation date)':'2026-10-01 09:30:00',
                        'Departamento':'AREQUIPA','DEPARTAMENTO':'','Nombre de Site':'A'}],date(2026,10,13))
    assert result['meses']=={'2026-10':1}
    assert result['departamentos']==[('AREQUIPA',1)]
    assert result['tipos']['Producción']=={'PLM':1}


def test_admite_lectura_por_lotes_sin_limitar_meses():
    rows=({'_key':f'CM-{i}','OPERATE PHASE':'close','FECHA DE CREACION':'2025-01-01'} for i in range(20001))
    result=indicadores(rows,date(2026,10,13))
    assert result['total']==20001
    assert result['meses']=={'2025-01':20001}


def test_fecha_sin_cero_inicial_con_hora():
    result=indicadores([{'_key':'CM-8','OPERATE PHASE':'close','FECHA DE CREACION':'1/10/2026 08:30:00'}],date(2026,10,13))
    assert result['meses']=={'2026-10':1}


def test_dimensiones_operativas_y_fecha_diaria_usan_columnas_reales():
    result = indicadores([{
        '_key':'CM-DIMENSIONES','Operate Phase':'close',
        'Fecha de creación (WO Creation date)':'13/10/2026 08:30',
        'Tipo tarea':'ENERGIA_AUSENCIA', 'Nombre de personal FLM asignado':'TÉCNICO FLM',
        'TECNICO ASIGNADO':'OTRO NOMBRE', 'O&M asignado':'GESTOR',
        'Prioridad del Site':'P1','Fault Level':'Alta',
    }], date(2026,10,13))
    row = result['detalle'][0]
    assert row['fecha'] == '2026-10-13'
    assert row['personal'] == 'TÉCNICO FLM'
    assert row['tarea'] == 'ENERGIA_AUSENCIA'
    assert row['prioridad'] == 'P1' and row['fault'] == 'Alta'


def test_dashboard_respeta_departamentos_permitidos(app,auth_client,cambiar_rol):
    import json
    import re
    from db import db
    from models import Proyecto,NucleusData,AccesoProyecto
    with auth_client.session_transaction() as session: uid=session['user_id']
    with app.app_context():
        proyecto=Proyecto.query.filter_by(nombre='FLM - ENTEL').one();pid=proyecto.id
        acceso=AccesoProyecto.query.filter_by(usuario_id=uid,proyecto_id=pid).first()
        if acceso is None:
            acceso=AccesoProyecto(usuario_id=uid,proyecto_id=pid);db.session.add(acceso)
        acceso.restricciones=json.dumps({'Departamento':['LIMA']})
        for key,departamento in [('CM-DASH-LIMA','LIMA'),('CM-DASH-CUSCO','CUSCO')]:
            db.session.add(NucleusData(proyecto_id=pid,key_value=key,data_json=json.dumps({'Departamento':departamento,'Operate Phase':'close','Fecha de creación (WO Creation date)':'2026-10-01'})))
        db.session.commit()
    cambiar_rol(auth_client, 'supervisor')
    with auth_client.session_transaction() as session:
        session['current_proyecto_id']=pid;session['current_proyecto_nombre']='FLM - ENTEL'
    response=auth_client.get('/analytics')
    assert response.status_code==200
    data=json.loads(re.search(r'<script id="di-data" type="application/json">(.*?)</script>',response.text,re.S).group(1))
    keys={r['wo'] for r in data['detalle']}
    assert 'CM-DASH-LIMA' in keys and 'CM-DASH-CUSCO' not in keys


def test_analytics_usa_flm_seleccionado_sin_mezclar_operadores(app, auth_client):
    import json
    import re
    from models import Proyecto, NucleusData
    from db import db
    with app.app_context():
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
    with app.app_context():
        db.session.add(NucleusData(proyecto_id=entel, key_value='ENTEL-DASH-QA', data_json=json.dumps({'OPERATE PHASE':'close','FECHA DE CREACION':'2026-09-01'})))
        db.session.commit()
    auth_client.get(f'/switch_project/{entel}')
    response = auth_client.get('/analytics')
    assert response.status_code == 200
    assert '<h1>Flm - Entel</h1>' in response.text
    assert 'Producción: Operate Phase' not in response.text
    assert '<nav class="flm-resource-bar"' not in response.text
    data = json.loads(re.search(r'<script id="di-data" type="application/json">(.*?)</script>', response.text, re.S).group(1))
    assert 'ENTEL-DASH-QA' in {row['wo'] for row in data['detalle']}
    assert 'OPERACIÓN · FLM - ENTEL' in response.text
    with auth_client.session_transaction() as session:
        assert session['current_proyecto_id'] == entel


def test_dashboard_desde_catalogo_usa_su_flm_de_origen(app, auth_client):
    from models import Proyecto
    with app.app_context():
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        material = Proyecto.query.filter_by(nombre='Material').one().id
    with auth_client.session_transaction() as session:
        session['current_proyecto_id'] = material
        session['current_proyecto_nombre'] = 'Material'
        session['flm_resource_context'] = {'catalogo_id':material, 'flm_id':entel, 'recurso':'material'}
    response = auth_client.get('/analytics')
    assert response.status_code == 200
    assert 'OPERACIÓN · FLM - ENTEL' in response.text


def test_dashboard_entel_no_consulta_el_flm_anterior(app, auth_client):
    import json
    import re
    from models import Proyecto, NucleusData
    from db import db
    with app.app_context():
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one().id
        integratel = Proyecto.query.filter_by(nombre='FLM - INTEGRATEL').one().id
        db.session.add(NucleusData(proyecto_id=entel, key_value='ENTEL-INDEPENDIENTE', data_json=json.dumps({'Operate Phase':'close','FECHA DE CREACION':'2026-10-01'})))
        db.session.add(NucleusData(proyecto_id=integratel, key_value='OTRO-OPERADOR', data_json='{}'))
        db.session.commit()
    auth_client.get(f'/switch_project/{integratel}')
    response = auth_client.get('/analytics')
    assert response.status_code == 200
    data = json.loads(re.search(r'<script id="di-data" type="application/json">(.*?)</script>', response.text, re.S).group(1))
    keys = {r['wo'] for r in data['detalle']}
    assert 'ENTEL-INDEPENDIENTE' in keys and 'OTRO-OPERADOR' not in keys
    assert data['produccion'] >= 1
    with auth_client.session_transaction() as session:
        assert session['current_proyecto_id'] == integratel
