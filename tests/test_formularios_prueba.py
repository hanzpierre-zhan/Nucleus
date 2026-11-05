import io
import json
import re
from pathlib import Path

import pytest
from flask import Flask
from PIL import Image

from db import db
from models import NucleusData, Proyecto


@pytest.fixture
def portal(tmp_path):
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.update(SECRET_KEY='clave-piloto-test', TESTING=True,
                      SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path / 'fuente.sqlite3'),
                      SQLALCHEMY_ENGINE_OPTIONS={}, FORM_PRUEBAS_ENABLED=True,
                      FORM_PRUEBAS_DIR=str(tmp_path / 'piloto'))
    db.init_app(app)
    from blueprints.formularios_prueba import bp
    app.register_blueprint(bp)
    from blueprints.auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    app.add_url_rule('/otro-modulo', view_func=lambda: 'No permitido al técnico')
    with app.app_context():
        db.create_all()
        personal = Proyecto(nombre='Dataper')
        rendicion = Proyecto(nombre='Rendicion')
        db.session.add_all([personal, rendicion]); db.session.flush()
        for doc, name, status in [('00001111', 'Ana Prueba', 'ACTIVO'),
                                  ('00002222', 'Luis Prueba', 'ACTIVO'),
                                  ('00003333', 'Cesado Prueba', 'CESADO')]:
            db.session.add(NucleusData(proyecto_id=personal.id, key_value=doc,
                data_json=json.dumps(dict(DOCUMENTO=doc, TECNICO=name, ESTADO=status,
                                          PROYECTO='FLM - ENTEL', DEPARTAMENTO='LIMA'))))
        for key, doc, amount, status in [('p1','00001111','250.50','DEPOSITADO'),
                                         ('p2','00002222','900.00','DEPOSITADO'),
                                         ('p3','00001111','100.00','CON SUSTENTO')]:
            db.session.add(NucleusData(proyecto_id=rendicion.id,key_value=key,
                data_json=json.dumps({'Documento del beneficiario':doc,
                                      'CODIGO DEPOSITO':'DEP-'+key,'MONTO PAGO':amount,
                                      'ESTADO':status,'Motivo de la solicitud':'Atención de prueba'})))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove(); db.engine.dispose()


def entrar(client, doc='00001111', clave=None):
    page = client.get('/form-pruebas/')
    token = re.search(rb'id="csrf" type="hidden" value="([^"]+)"', page.data).group(1).decode()
    response = client.post('/form-pruebas/ingresar', json={'documento':doc,'clave':clave or doc},
                           headers={'X-CSRF-Token':token})
    return response


def headers(client):
    with client.session_transaction() as s:
        return {'X-CSRF-Token':s['form_csrf']}


def imagen():
    out = io.BytesIO(); Image.new('RGB',(30,30),'white').save(out,'PNG'); out.seek(0)
    return out


def solicitud(client, nonce='a'*32):
    gastos = client.get('/form-pruebas/datos').json['gastos']
    return client.post('/form-pruebas/solicitar', json={
        'nonce':nonce,'tipo_gasto':gastos[0],'monto':'30.50','motivo':'Movilidad',
        'medio_pago':'Yape','cuenta':'999999999','personal':{'documento':'00002222'}},headers=headers(client))


def fuente(app):
    with app.app_context():
        return [(r.id,r.data_json) for r in NucleusData.query.order_by(NucleusData.id)]


def test_solicitud_ampliada_usa_identidad_y_catalogo_del_proyecto(portal):
    from services.formularios_prueba import almacen

    with portal.app_context():
        for nombre in ('FLM - ENTEL', 'FLM - CLARO', 'FLM - INTEGRATEL', 'FLM - PEXT'):
            proyecto = Proyecto(nombre=nombre)
            db.session.add(proyecto)
            db.session.flush()
            db.session.add(NucleusData(proyecto_id=proyecto.id, key_value='CM-' + nombre.split()[-1],
                                       data_json=json.dumps({'Site Name': 'Torre ' + nombre.split()[-1]})))
        db.session.commit()

    client = portal.test_client()
    assert entrar(client).status_code == 200
    assert client.get('/form-pruebas/datos').json['proyecto_default'] == 'ENTEL'
    for proyecto in ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT'):
        assert client.get(f'/form-pruebas/sugerencias?proyecto={proyecto}&campo=wo&q=CM').json == {
            'opciones': [f'CM-{proyecto}']}
        assert client.get(f'/form-pruebas/sugerencias?proyecto={proyecto}&campo=site&q=Torre').json == {
            'opciones': [f'Torre {proyecto}']}
    solicitud = {
        'nonce': 'b' * 32, 'proyecto': 'CLARO', 'presupuesto': 'Refacturable',
        'tipo_gasto': ['MATERIALES', 'PEAJE', 'COMPRAS', 'ALQUILER'],
        'detalle_compras': ['Consumibles', 'Herramientas'],
        'detalle_alquiler': ['Vehículos'],
        'monto': '30.50', 'motivo': 'Compra de repuestos',
        'tipo_billetera': 'Plin', 'numero_billetera': '999999999', 'titular': 'Ana Prueba',
        'cuenta_cci': '00123456789012345678', 'banco': 'Interbank',
        'dni': '00002222', 'responsable_validacion': 'MÓNICA', 'comentarios': 'Urgente',
    }
    for monto_invalido in ('adasfasf', 'S/ 30.50', '1e2', '30.555'):
        response = client.post('/form-pruebas/solicitar', headers=headers(client),
                               json=dict(solicitud, monto=monto_invalido))
        assert response.status_code == 400
    solicitud['partidas'] = [
        {'categoria': 'MATERIALES', 'detalle': '', 'monto': '10'},
        {'categoria': 'PEAJE', 'detalle': '', 'monto': '5,50'},
        {'categoria': 'COMPRAS', 'detalle': 'Consumibles', 'monto': '5'},
        {'categoria': 'COMPRAS', 'detalle': 'Herramientas', 'monto': '10'},
        {'categoria': 'ALQUILER', 'detalle': 'Vehículos', 'monto': '50'},
    ]
    incompleta = dict(solicitud, partidas=solicitud['partidas'][:-1])
    assert client.post('/form-pruebas/solicitar', headers=headers(client), json=incompleta).status_code == 400
    response = client.post('/form-pruebas/solicitar', headers=headers(client), json=solicitud)
    assert response.status_code == 201, response.json
    with portal.app_context(), almacen() as con:
        datos = json.loads(con.execute('SELECT datos FROM envios').fetchone()['datos'])
    assert datos['dni'] == '00001111'
    assert datos['tipo_gasto'] == 'MATERIALES, PEAJE, COMPRAS, ALQUILER'
    assert datos['monto'] == '80.50' and len(datos['partidas']) == 5
    assert datos['detalle_gasto'] == {'COMPRAS': ['Consumibles', 'Herramientas'], 'ALQUILER': ['Vehículos']}
    assert datos['proyecto'] == 'CLARO' and datos['presupuesto'] == 'Refacturable'
    assert datos['numero_billetera'] == '999999999' and datos['cuenta_cci'] == solicitud['cuenta_cci']
    assert datos['responsable_validacion'] == 'MÓNICA' and datos['comentarios'] == 'Urgente'
    sin_pago = dict(solicitud, nonce='c' * 32, tipo_billetera='No aplica', numero_billetera='')
    sin_pago.pop('motivo')
    assert client.post('/form-pruebas/solicitar', headers=headers(client), json=sin_pago).status_code == 201
    transferencia = dict(sin_pago, nonce='d' * 32)
    for invalida in (dict(transferencia, cuenta_cci='123456789'), dict(transferencia, banco=''),
                     dict(transferencia, banco='Banco no listado'),
                     dict(transferencia, tipo_billetera='Yape', numero_billetera='123')):
        assert client.post('/form-pruebas/solicitar', headers=headers(client), json=invalida).status_code == 400
    respuesta = client.post('/form-pruebas/solicitar', headers=headers(client), json=transferencia)
    assert respuesta.status_code == 201
    with portal.app_context(), almacen() as con:
        guardado = json.loads(con.execute('SELECT datos FROM envios WHERE id=?', (respuesta.json['id'],)).fetchone()['datos'])
    assert guardado['cuenta_cci'] == transferencia['cuenta_cci'] and guardado['banco'] == 'Interbank'
    assert guardado['numero_billetera'] == ''


def test_identidad_solo_formularios_y_datos_propios(portal):
    client=portal.test_client()
    assert entrar(client).status_code==200
    page=client.get('/form-pruebas/')
    assert b'Solicitar' in page.data and b'Rendir' in page.data
    assert b'app-sidebar' not in page.data
    info=client.get('/form-pruebas/datos').json
    assert info['total']=='250.50'
    assert [d['codigo'] for d in info['depositos']]==['DEP-p1']
    assert client.get('/otro-modulo').status_code==302
    assert client.post('/api/import/process').status_code==403
    with client.session_transaction() as s:
        assert not s.get('user_id')


def test_escrituras_aisladas_fotos_y_reintento(portal):
    before=fuente(portal); client=portal.test_client(); entrar(client)
    response=solicitud(client); assert response.status_code==201,response.json
    again=solicitud(client); assert again.status_code==200 and again.json['id']==response.json['id']
    deposit=client.get('/form-pruebas/datos').json['depositos'][0]
    data={'nonce':'b'*32,'referencia':deposit['referencia'],'monto':'100.50','detalle':'Movilidad y materiales',
          'fotos':(imagen(),'recibo.png')}
    sent=client.post('/form-pruebas/rendir',data=data,headers=headers(client))
    assert sent.status_code==201,sent.json
    info=client.get('/form-pruebas/datos').json
    assert info['total']=='150.00' and len(info['recientes'])==2
    retry=client.post('/form-pruebas/rendir',data={'nonce':'b'*32},headers=headers(client))
    assert retry.status_code==200 and retry.json['id']==sent.json['id']
    from services.formularios_prueba import almacen
    with portal.app_context(), almacen() as con:
        rows=con.execute('SELECT documento,datos FROM envios').fetchall()
        assert len(rows)==2 and all(r['documento']=='00001111' for r in rows)
        photo=json.loads(rows[1]['datos'])['fotos'][0]
    assert client.get('/form-pruebas/foto/'+photo).status_code==200
    other=portal.test_client(); entrar(other,'00002222')
    assert other.get('/form-pruebas/foto/'+photo).status_code==404
    forged=other.post('/form-pruebas/rendir',data={'nonce':'c'*32,'referencia':deposit['referencia'],
        'monto':'1','detalle':'No permitido','fotos':(imagen(),'foto.png')},headers=headers(other))
    assert forged.status_code==403
    assert fuente(portal)==before


def test_validacion_sesion_csrf_y_saldo(portal):
    client=portal.test_client()
    assert entrar(client,'00003333').status_code==401
    assert entrar(client,clave='incorrecta').status_code==401
    assert entrar(client).status_code==200
    assert client.post('/form-pruebas/solicitar',json={}).status_code==403
    deposit=client.get('/form-pruebas/datos').json['depositos'][0]
    result=client.post('/form-pruebas/rendir',data={'nonce':'d'*32,'referencia':deposit['referencia'],
        'monto':'999','detalle':'Mayor al saldo','fotos':(imagen(),'foto.png')},headers=headers(client))
    assert result.status_code==400
    invalid=client.post('/form-pruebas/rendir',data={'nonce':'e'*32,'referencia':deposit['referencia'],
        'monto':'1','detalle':'Foto inválida','fotos':(io.BytesIO(b'no es una imagen'),'foto.jpg')},headers=headers(client))
    assert invalid.status_code==400
    with portal.app_context():
        row=NucleusData.query.filter_by(key_value='00001111').one()
        data=json.loads(row.data_json);data['ESTADO']='CESADO';row.data_json=json.dumps(data);db.session.commit()
    assert client.get('/form-pruebas/datos').status_code==401


def test_deshabilitado_por_defecto_no_abre_acceso(portal):
    portal.config['FORM_PRUEBAS_ENABLED']=False
    assert portal.test_client().get('/form-pruebas/').status_code==404


def test_login_habitual_documento_como_usuario_y_clave(portal):
    before=fuente(portal)
    client=portal.test_client()
    response=client.post('/login',data={'username':'00001111','password':'00001111'})
    assert response.status_code==302
    assert response.headers['Location'].endswith('/form-pruebas/')
    assert client.get('/form-pruebas/datos').json['personal']['documento']=='00001111'
    with client.session_transaction() as s:
        assert not s.get('user_id') and s['form_documento']=='00001111'
    assert fuente(portal)==before
    other=portal.test_client()
    assert other.post('/login',data={'username':'00003333','password':'00003333'}).status_code==200
    assert other.get('/form-pruebas/datos').status_code==401
