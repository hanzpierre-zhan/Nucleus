import io
import json
import re
from pathlib import Path

import pytest
from flask import Flask
from PIL import Image

from db import db
from models import AccesoProyecto, NucleusData, Proyecto, Usuario


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
        claro = Usuario(nombre='Mónica Prueba', username='monica', password_hash='no-login')
        entel = Usuario(nombre='Luis Prueba', username='luis', password_hash='no-login')
        db.session.add_all([claro, entel])
        db.session.flush()
        ids = {'CLARO': claro.id, 'ENTEL': entel.id}
        for familia, uid in ids.items():
            pid = Proyecto.query.filter_by(nombre=f'FLM - {familia}').one().id
            db.session.add(AccesoProyecto(usuario_id=uid, proyecto_id=pid))
        db.session.commit()

    client = portal.test_client()
    assert entrar(client).status_code == 200
    datos_portal = client.get('/form-pruebas/datos').json
    assert datos_portal['proyecto_default'] == 'ENTEL'
    assert datos_portal['responsables_validacion'] == {
        'CLARO': {str(ids['CLARO']): 'Mónica Prueba'},
        'ENTEL': {str(ids['ENTEL']): 'Luis Prueba'}, 'INTEGRATEL': {}, 'PEXT': {},
    }
    for proyecto in ('ENTEL', 'CLARO', 'INTEGRATEL', 'PEXT'):
        assert client.get(f'/form-pruebas/sugerencias?proyecto={proyecto}&campo=wo&q=CM').json == {
            'opciones': [f'CM-{proyecto}']}
        assert client.get(f'/form-pruebas/sugerencias?proyecto={proyecto}&campo=site&q=Torre').json == {
            'opciones': [f'Torre {proyecto}']}
    solicitud = {
        'nonce': 'b' * 32, 'proyecto': 'CLARO', 'presupuesto': 'Refacturable',
        'tipo_gasto': ['MATERIALES', 'PEAJE', 'COMPRAS', 'ALQUILER'],
        'detalle_compras': ['Consumibles', 'Equipos y accesorios'],
        'detalle_alquiler': ['Equipos', 'Generadores'],
        'monto': '30.50', 'motivo': 'Compra de repuestos',
        'tipo_billetera': 'Plin', 'numero_billetera': '999999999', 'titular': 'Ana Prueba',
        'cuenta_cci': '00123456789012345678', 'banco': 'Interbank',
        'dni': '00002222', 'responsable_validacion': str(ids['CLARO']), 'comentarios': 'Urgente',
    }
    for monto_invalido in ('adasfasf', 'S/ 30.50', '1e2', '30.555'):
        response = client.post('/form-pruebas/solicitar', headers=headers(client),
                               json=dict(solicitud, monto=monto_invalido))
        assert response.status_code == 400
    solicitud['partidas'] = [
        {'categoria': 'MATERIALES', 'detalle': '', 'monto': '10'},
        {'categoria': 'PEAJE', 'detalle': '', 'monto': '5,50'},
        {'categoria': 'COMPRAS', 'detalle': 'Consumibles', 'monto': '5'},
        {'categoria': 'COMPRAS', 'detalle': 'Equipos y accesorios', 'monto': '10'},
        {'categoria': 'ALQUILER', 'detalle': 'Equipos', 'monto': '20'},
        {'categoria': 'ALQUILER', 'detalle': 'Generadores', 'monto': '30'},
    ]
    incompleta = dict(solicitud, partidas=solicitud['partidas'][:-1])
    assert client.post('/form-pruebas/solicitar', headers=headers(client), json=incompleta).status_code == 400
    responsable_invalido = dict(solicitud, responsable_validacion=str(ids['ENTEL']))
    rechazo = client.post('/form-pruebas/solicitar', headers=headers(client), json=responsable_invalido)
    assert rechazo.status_code == 400 and 'asignado al proyecto' in rechazo.json['error']
    response = client.post('/form-pruebas/solicitar', headers=headers(client), json=solicitud)
    assert response.status_code == 201, response.json
    with portal.app_context(), almacen() as con:
        datos = json.loads(con.execute('SELECT datos FROM envios').fetchone()['datos'])
    assert datos['dni'] == '00001111'
    assert datos['tipo_gasto'] == 'MATERIALES, PEAJE, COMPRAS, ALQUILER'
    assert datos['monto'] == '80.50' and len(datos['partidas']) == 6
    assert datos['detalle_gasto'] == {'COMPRAS': ['Consumibles', 'Equipos y accesorios'],
                                    'ALQUILER': ['Equipos', 'Generadores']}
    assert datos['proyecto'] == 'CLARO' and datos['presupuesto'] == 'Refacturable'
    assert datos['numero_billetera'] == '999999999' and datos['cuenta_cci'] == solicitud['cuenta_cci']
    assert datos['responsable_validacion'] == 'Mónica Prueba' and datos['comentarios'] == 'Urgente'
    assert datos['responsable_validacion_id'] == ids['CLARO']
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


def test_historial_pago_rechazo_y_foto_privada(portal, monkeypatch):
    from blueprints import rendicion

    with portal.app_context():
        admin = Usuario(username='admin-piloto', password_hash='no-login', rol='zeno')
        db.session.add(admin)
        fila = NucleusData.query.filter_by(key_value='p1').one()
        registro = json.loads(fila.data_json)
        registro['FOTO PAGO'] = f'/api/rendicion/foto/{fila.proyecto_id}/p1/rendicion_pago.jpg'
        fila.data_json = json.dumps(registro)
        db.session.commit()
        admin_id, registro_id = admin.id, fila.id
    monkeypatch.setattr(rendicion, '_servir_foto_rendicion', lambda pid, key, nombre: (nombre, 200))

    tecnico = portal.test_client()
    assert entrar(tecnico).status_code == 200
    pagada = solicitud(tecnico).json
    rechazada = solicitud(tecnico, nonce='e' * 32).json
    assert pagada['codigo'].startswith('PRUEBA-') and pagada['monto'] == '30.50'
    admin = portal.test_client()
    with admin.session_transaction() as sesion:
        sesion.update(user_id=admin_id, form_csrf='prueba-csrf')
    assert admin.post('/form-pruebas/administrar', data={
        'csrf': 'prueba-csrf', 'accion': 'pagar', 'id': pagada['id'],
        'comprobante': (imagen(), 'pago.png'),
    }).status_code == 302
    assert admin.post('/form-pruebas/administrar', data={
        'csrf': 'prueba-csrf', 'accion': 'rechazar', 'id': rechazada['id'], 'motivo': 'Revisar importe',
    }).status_code == 302

    datos = tecnico.get('/form-pruebas/datos').json
    historial = {r['codigo']: r for r in datos['historial']}
    assert historial[pagada['codigo']]['estado'] == 'Pagado'
    assert historial[rechazada['codigo']]['rechazo'] == 'Revisar importe'
    assert any(d['codigo'] == pagada['codigo'] for d in datos['depositos'])
    foto_piloto = historial[pagada['codigo']]['foto']
    foto_real = f'/form-pruebas/deposito/registro/{registro_id}/foto'
    assert tecnico.get(foto_piloto).mimetype == 'image/jpeg'
    assert tecnico.get(foto_real).get_data(as_text=True) == 'rendicion_pago.jpg'
    otro = portal.test_client()
    assert entrar(otro, doc='00002222').status_code == 200
    assert otro.get(foto_piloto).status_code == 404
    assert otro.get(foto_real).status_code == 404


def test_identidad_solo_formularios_y_datos_propios(portal):
    with portal.app_context():
        original = NucleusData.query.filter_by(key_value='p1').one()
        datos = json.loads(original.data_json)
        for estado in ('RECHAZADO', 'ANULADO'):
            registro = dict(datos, ESTADO=estado, _RECHAZO_ETAPA='EVIDENCIA')
            registro['CODIGO DEPOSITO'] = 'DEP-' + estado
            db.session.add(NucleusData(proyecto_id=original.proyecto_id, key_value=estado,
                                       data_json=json.dumps(registro)))
        db.session.commit()
    client=portal.test_client()
    assert entrar(client).status_code==200
    page=client.get('/form-pruebas/')
    assert b'Solicitar' in page.data and b'Rendir' in page.data
    assert b'app-sidebar' not in page.data
    info=client.get('/form-pruebas/datos').json
    assert info['total']=='250.50'
    assert [d['codigo'] for d in info['depositos']]==['DEP-p1']
    estados = {r['codigo']: r['estado_rendicion'] for r in info['historial'] if 'estado_rendicion' in r}
    assert estados['DEP-RECHAZADO'] == 'Rechazado' and estados['DEP-ANULADO'] == 'Anulado'
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


def test_rendicion_con_comprobantes_por_concepto_y_evidencia(portal):
    from services.formularios_prueba import almacen, guardar

    client = portal.test_client()
    assert entrar(client).status_code == 200
    with portal.app_context():
        fila = NucleusData.query.filter_by(key_value='p1').one()
        datos = json.loads(fila.data_json)
        datos['Tipo de gasto'] = 'PASAJE, MATERIAL'
        fila.data_json = json.dumps(datos)
        db.session.commit()
        guardar('00001111', 'solicitud', {
            'estado': 'Pagado', 'monto': '30.00', 'motivo': 'Viaje y materiales',
            'partidas': [
                {'categoria': 'PASAJE', 'detalle': '', 'monto': '10.00'},
                {'categoria': 'MATERIALES', 'detalle': '', 'monto': '20.00'},
            ],
        }, 'a' * 32, 'f' * 32)
    depositos = client.get('/form-pruebas/datos').json['depositos']
    historico = next(d for d in depositos if d['codigo'] == 'DEP-p1')
    assert [p['etiqueta'] for p in historico['partidas']] == ['Pasajes', 'Compra de materiales']
    assert all('monto' not in p for p in historico['partidas'])
    deposit = next(d for d in depositos if d['codigo'].startswith('PRUEBA-'))
    assert [p['etiqueta'] for p in deposit['partidas']] == ['Pasajes', 'Compra de materiales']
    grupos = [
        [{'tipo': 'Boleta'}, {'tipo': 'Boleta'}],
        [{'tipo': 'Factura'}],
    ]
    data = {'nonce': 'b' * 32, 'referencia': deposit['referencia'], 'monto': '30.00'}
    invalid = client.post('/form-pruebas/rendir', headers=headers(client), data={
        **data, 'comprobantes': json.dumps(grupos),
        'comprobante-0-0': (imagen(), 'boleta.png'),
        'comprobante-0-1': (imagen(), 'otra.png'),
        'comprobante-1-0': (imagen(), 'factura.png'),
    })
    assert invalid.status_code == 400 and 'RUC' in invalid.json['error']
    grupos[1][0]['ruc'] = '20123456789'
    result = client.post('/form-pruebas/rendir', headers=headers(client), data={
        **data, 'comprobantes': json.dumps(grupos),
        'comprobante-0-0': (imagen(), 'boleta.png'),
        'comprobante-0-1': (imagen(), 'otra.png'),
        'comprobante-1-0': (imagen(), 'factura.png'),
        'evidencia': [(imagen(), 'trabajo.png'), (imagen(), 'material.png')],
    })
    assert result.status_code == 201, result.json
    with portal.app_context(), almacen() as con:
        saved = json.loads(con.execute("SELECT datos FROM envios WHERE tipo='rendicion'").fetchone()['datos'])
    comprobantes = [c for p in saved['partidas'] for c in p['comprobantes']]
    assert [c['tipo'] for c in comprobantes] == ['Boleta', 'Boleta', 'Factura']
    assert comprobantes[-1]['ruc'] == '20123456789'
    assert [c['foto'] for c in comprobantes] + saved['evidencia'] == saved['fotos']
    assert len(set(saved['fotos'])) == 5


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
