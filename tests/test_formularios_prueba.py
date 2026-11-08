import io
import json
import re
from pathlib import Path
from zipfile import ZipFile

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
                                  ('00003333', 'Cesado Prueba', 'CESADO'),
                                  ('00004444', 'Nuevo Prueba', 'ACTIVO')]:
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
        # Clave vigente (igual al documento) para los técnicos de los demás tests;
        # 00004444 no tiene clave guardada: ingresa con su DNI y debe cambiarla.
        from werkzeug.security import generate_password_hash
        from models import ClaveTecnico
        for doc in ('00001111', '00002222', '00003333'):
            db.session.add(ClaveTecnico(documento=doc, clave_hash=generate_password_hash(doc)))
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
            if nombre == 'FLM - CLARO':
                db.session.add(NucleusData(proyecto_id=proyecto.id, key_value='123456789', data_json='{}'))
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
        assert client.get(f'/form-pruebas/sugerencias?proyecto={proyecto}&campo=wo&q=1234').json == {
            'opciones': ['123456789'] if proyecto == 'CLARO' else []}
    solicitud = {
        'nonce': 'b' * 32, 'proyecto': 'CLARO',
        'tipo_gasto': ['MATERIALES', 'PEAJE', 'COMPRAS', 'ALQUILER'],
        'detalle_compras': ['Consumibles', 'Accesorios'],
        'detalle_alquiler': ['Equipos especiales de medición', 'Generadores eléctricos - Refacturable'],
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
        {'categoria': 'COMPRAS', 'detalle': 'Accesorios', 'monto': '10'},
        {'categoria': 'ALQUILER', 'detalle': 'Equipos especiales de medición', 'monto': '20'},
        {'categoria': 'ALQUILER', 'detalle': 'Generadores eléctricos - Refacturable', 'monto': '30'},
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
    assert datos['detalle_gasto'] == {'COMPRAS': ['Consumibles', 'Accesorios'],
                                    'ALQUILER': ['Equipos especiales de medición', 'Generadores eléctricos - Refacturable']}
    assert datos['proyecto'] == 'CLARO' and datos['presupuesto'] == 'Mixto'
    assert [p['presupuesto'] for p in datos['partidas']] == ['Gasto Cobra'] * 5 + ['Refacturable']
    pext = client.post('/form-pruebas/solicitar', headers=headers(client),
                       json=dict(solicitud, nonce='f' * 32, proyecto='PEXT', responsable_validacion=''))
    assert pext.status_code == 400 and 'no está disponible para PEXT' in pext.json['error']
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
        gestora = Usuario(username='gestora-piloto', password_hash='no-login', rol='gestor')
        proyecto = Proyecto(nombre='FLM - ENTEL')
        db.session.add_all([admin, gestora, proyecto])
        db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=gestora.id, proyecto_id=proyecto.id))
        fila = NucleusData.query.filter_by(key_value='p1').one()
        registro = json.loads(fila.data_json)
        registro['FOTO PAGO'] = f'/api/rendicion/foto/{fila.proyecto_id}/p1/rendicion_pago.jpg'
        fila.data_json = json.dumps(registro)
        db.session.commit()
        admin_id, gestora_id, registro_id = admin.id, gestora.id, fila.id
    monkeypatch.setattr(rendicion, '_servir_foto_rendicion', lambda pid, key, nombre: (nombre, 200))

    tecnico = portal.test_client()
    assert entrar(tecnico).status_code == 200
    pagada = solicitud(tecnico).json
    rechazada = solicitud(tecnico, nonce='e' * 32).json
    assert pagada['codigo'].startswith('PRUEBA-') and pagada['monto'] == '30.50'
    admin = portal.test_client()
    with admin.session_transaction() as sesion:
        sesion.update(user_id=admin_id, form_csrf='prueba-csrf')
    validacion = portal.test_client()
    with validacion.session_transaction() as sesion:
        sesion.update(user_id=gestora_id, form_csrf='prueba-csrf')
    assert validacion.get('/form-pruebas/gestion/depositos').status_code == 403
    assert admin.post('/form-pruebas/gestion/depositos', data={
        'csrf': 'prueba-csrf', 'accion': 'pagar', 'id': pagada['id'],
        'comprobante': (imagen(), 'pago.png'),
    }).status_code == 409
    assert pagada['codigo'] in validacion.get('/form-pruebas/gestion/validacion').text
    assert validacion.post('/form-pruebas/gestion/validacion', data={
        'csrf': 'prueba-csrf', 'accion': 'aprobar', 'id': pagada['id'],
    }).status_code == 302
    assert pagada['codigo'] in admin.get('/form-pruebas/gestion/depositos').text
    assert admin.post('/form-pruebas/gestion/depositos', data={
        'csrf': 'prueba-csrf', 'accion': 'pagar', 'id': pagada['id'],
        'comprobante': (imagen(), 'pago.png'),
    }).status_code == 302
    assert admin.post('/form-pruebas/gestion/validacion', data={
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
    data={'nonce':'b'*32,'referencia':deposit['referencia'],'comprobantes':'[[]]',
          'monto_devolucion':'250.50','motivo_devolucion':'No se realizó el trabajo',
          'foto_devolucion':(imagen(),'devolucion.png')}
    sent=client.post('/form-pruebas/rendir',data=data,headers=headers(client))
    assert sent.status_code==201,sent.json
    info=client.get('/form-pruebas/datos').json
    assert info['total']=='0' and len(info['recientes'])==2
    retry=client.post('/form-pruebas/rendir',data={'nonce':'b'*32},headers=headers(client))
    assert retry.status_code==200 and retry.json['id']==sent.json['id']
    from services.formularios_prueba import almacen
    with portal.app_context(), almacen() as con:
        rows=con.execute('SELECT documento,datos FROM envios').fetchall()
        assert len(rows)==2 and all(r['documento']=='00001111' for r in rows)
        guardado=json.loads(rows[1]['datos'])
        assert guardado['gastado']=='0.00' and guardado['devolucion']['monto']=='250.50'
        photo=guardado['devolucion']['foto']
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
        [{'tipo': 'Boleta', 'monto': '5.50'}, {'tipo': 'Boleta', 'monto': '4.50'}],
        [{'tipo': 'Factura', 'monto': '15.00'}],
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
    for devolucion, mensaje in [({}, 'Registra una devolución'), ({'monto_devolucion': '4.99'}, 'exactamente'),
                                ({'monto_devolucion': '5.00', 'motivo_devolucion': 'Sobrante'}, 'Adjunta la foto')]:
        rechazo = client.post('/form-pruebas/rendir', headers=headers(client), data={
            **data, **devolucion, 'comprobantes': json.dumps(grupos),
            'comprobante-0-0': (imagen(), 'boleta.png'),
            'comprobante-0-1': (imagen(), 'otra.png'),
            'comprobante-1-0': (imagen(), 'factura.png'),
        })
        assert rechazo.status_code == 400 and mensaje in rechazo.json['error']
    result = client.post('/form-pruebas/rendir', headers=headers(client), data={
        **data, 'comprobantes': json.dumps(grupos),
        'comprobante-0-0': (imagen(), 'boleta.png'),
        'comprobante-0-1': (imagen(), 'otra.png'),
        'comprobante-1-0': (imagen(), 'factura.png'),
        'monto_devolucion': '5.00', 'motivo_devolucion': 'Sobrante',
        'foto_devolucion': (imagen(), 'devolucion.png'),
        'evidencia_por_comprobante': '1',
        'evidencia-0-0': (imagen(), 'trabajo.png'),
        'evidencia-0-1': (imagen(), 'material.png'),
        'evidencia-1-0': (imagen(), 'uso.png'),
    })
    assert result.status_code == 201, result.json
    assert result.json['fotos_comprobante_repetidas'] == 2
    with portal.app_context(), almacen() as con:
        saved = json.loads(con.execute("SELECT datos FROM envios WHERE tipo='rendicion'").fetchone()['datos'])
    comprobantes = [c for p in saved['partidas'] for c in p['comprobantes']]
    assert [c['tipo'] for c in comprobantes] == ['Boleta', 'Boleta', 'Factura']
    assert [c['foto_repetida'] for c in comprobantes] == [False, True, True]
    assert comprobantes[-1]['ruc'] == '20123456789'
    assert saved['gastado'] == '25.00' and saved['devolucion']['monto'] == '5.00'
    assert [c['foto'] for c in comprobantes] + saved['evidencia'] + [saved['devolucion']['foto']] == saved['fotos']
    assert [c['evidencia'] for c in comprobantes] == saved['evidencia']
    assert len(set(saved['fotos'])) == 7
    with portal.app_context():
        usuario = Usuario(username='revisor', nombre='Revisor', password_hash='no-login', rol='admin')
        db.session.add(usuario)
        db.session.flush()
        uid = usuario.id
        db.session.commit()
    foto_revision = f"/form-pruebas/administrar/rendicion/{result.json['id']}/foto/{comprobantes[1]['foto']}"
    assert client.get(foto_revision).status_code == 302
    revisor = portal.test_client()
    with revisor.session_transaction() as sesion:
        sesion['user_id'] = uid
    assert revisor.get(foto_revision).mimetype == 'image/jpeg'


def test_consulta_ruc_usa_padron_importado(portal, tmp_path, monkeypatch):
    from scripts.importar_padron_ruc import importar
    from services import formularios_prueba

    monkeypatch.setattr(formularios_prueba, 'consultar_ruc_externo', lambda *args: None)

    client = portal.test_client()
    ruta = '/form-pruebas/ruc/20123456789'
    assert client.get(ruta).status_code == 401
    assert entrar(client).status_code == 200
    assert client.get(ruta).json == {'resultado': 'no_disponible'}
    origen = tmp_path / 'padron.zip'
    with ZipFile(origen, 'w') as archivo:
        archivo.writestr('padron.txt', (
            'RUC|NOMBRE O RAZÓN SOCIAL|ESTADO DEL CONTRIBUYENTE|CONDICIÓN DE DOMICILIO|UBIGEO|\n'
            '20123456789|EMISIÓN DE PRUEBA SAC|ACTIVO|HABIDO|150101|\n'
            '10987654321|OTRO EMISOR|BAJA DEFINITIVA|HABIDO|150101|\n'
        ).encode('latin-1'))
    assert importar(origen, Path(portal.config['FORM_PRUEBAS_DIR']) / 'padron-ruc.sqlite3') == 2
    assert client.get(ruta).json == {'resultado': 'encontrado', 'razon_social': 'EMISIÓN DE PRUEBA SAC',
                                    'activo': True}
    assert client.get('/form-pruebas/ruc/10987654321').json['activo'] is False
    assert client.get('/form-pruebas/ruc/20000000000').json == {'resultado': 'no_encontrado'}


def test_consulta_ruc_prioriza_openruc_para_empresas(portal, monkeypatch):
    from services import formularios_prueba

    llamadas = []
    respuestas = {
        'openruc.com': (200, {'razon_social': 'Empresa Prueba', 'estado': 'ACTIVO'}),
        'ruc.kembec.com': (200, {'nombre-o-razon-social': 'Proveedor Prueba',
                                'estado-del-contribuyente': 'BAJA DEFINITIVA'}),
    }

    class Conexion:
        def __init__(self, host, timeout):
            self.host = host

        def request(self, metodo, recurso, headers):
            llamadas.append((self.host, recurso, headers.get('Authorization')))

        def getresponse(self):
            estado, datos = respuestas[self.host]
            return type('Respuesta', (), {
                'status': estado, 'read': lambda _, limite: json.dumps(datos).encode()
            })()

        def close(self):
            pass

    monkeypatch.setattr(formularios_prueba, 'HTTPSConnection', Conexion)
    client = portal.test_client()
    assert entrar(client).status_code == 200
    assert client.get('/form-pruebas/ruc/20123456789').json == {
        'resultado': 'encontrado', 'razon_social': 'Empresa Prueba', 'activo': True,
    }
    assert llamadas == [('openruc.com', '/api/ruc/20123456789', None)]
    assert client.get('/form-pruebas/ruc/10123456789').json == {
        'resultado': 'encontrado', 'razon_social': 'Proveedor Prueba', 'activo': False,
    }
    assert llamadas[1:] == [('ruc.kembec.com', '/api/search/10123456789', None)]
    respuestas['openruc.com'] = (503, {})
    assert client.get('/form-pruebas/ruc/20123456789').json == {'resultado': 'no_disponible'}


def test_validacion_sesion_csrf_y_saldo(portal):
    client=portal.test_client()
    assert entrar(client,'00003333').status_code==401
    assert entrar(client,clave='incorrecta').status_code==401
    assert entrar(client).status_code==200
    assert client.post('/form-pruebas/solicitar',json={}).status_code==403
    deposit=client.get('/form-pruebas/datos').json['depositos'][0]
    result=client.post('/form-pruebas/rendir',data={'nonce':'d'*32,'referencia':deposit['referencia'],
        'comprobantes':'[[{"tipo":"Boleta","monto":"999"}]]',
        'comprobante-0-0':(imagen(),'foto.png')},headers=headers(client))
    assert result.status_code==400
    invalid=client.post('/form-pruebas/rendir',data={'nonce':'e'*32,'referencia':deposit['referencia'],
        'comprobantes':'[[{"tipo":"Boleta","monto":"250.50"}]]',
        'comprobante-0-0':(io.BytesIO(b'no es una imagen'),'foto.jpg')},headers=headers(client))
    assert invalid.status_code==400
    exacto=client.post('/form-pruebas/rendir',data={'nonce':'e'*32,'referencia':deposit['referencia'],
        'comprobantes':'[[{"tipo":"Boleta","monto":"250.50"}]]',
        'comprobante-0-0':(imagen(),'foto.png')},headers=headers(client))
    assert exacto.status_code==201,exacto.json
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


def test_login_movil_de_gestora_entra_a_nucleus_no_al_portal(portal):
    """El diseño del portal es solo para el personal de Dataper."""
    from werkzeug.security import generate_password_hash

    portal.add_url_rule('/analytics', endpoint='pages.analytics', view_func=lambda: 'Nucleus')
    with portal.app_context():
        cuenta = Usuario(username='gestora-movil', rol='gestor',
                         password_hash=generate_password_hash('prueba-movil'))
        db.session.add(cuenta)
        db.session.commit()
    client = portal.test_client()
    headers_movil = {'User-Agent': 'Mozilla/5.0 (iPhone) Mobile Safari'}
    respuesta = client.post('/login', data={'username': 'gestora-movil', 'password': 'prueba-movil'},
                            headers=headers_movil)
    assert b'name="legal_accept"' in respuesta.data
    respuesta = client.post('/login', data={'consent_step': '1', 'legal_accept': '1'}, headers=headers_movil)
    assert respuesta.headers['Location'] == '/analytics'


def test_por_rendir_agrupa_y_ordena_depositos_del_proyecto(portal):
    with portal.app_context():
        gestora = Usuario(username='gestora-saldos', password_hash='no-login', rol='gestor')
        proyecto = Proyecto(nombre='FLM - ENTEL')
        db.session.add_all([gestora, proyecto])
        db.session.flush()
        db.session.add(AccesoProyecto(usuario_id=gestora.id, proyecto_id=proyecto.id))
        for clave in ('p1', 'p2', 'p3'):
            fila = NucleusData.query.filter_by(key_value=clave).one()
            datos = json.loads(fila.data_json)
            datos['Nombre del proyecto'] = 'FLM - ENTEL'
            fila.data_json = json.dumps(datos)
        datos['ESTADO'] = 'DEPOSITADO'
        datos['CODIGO DEPOSITO'] = 'DEP-FUERA'
        datos['Nombre del proyecto'] = 'FLM - CLARO'
        db.session.add(NucleusData(proyecto_id=fila.proyecto_id, key_value='fuera-saldos', data_json=json.dumps(datos)))
        db.session.commit()
        uid = gestora.id
    antes = fuente(portal)
    client = portal.test_client()
    with client.session_transaction() as session:
        session['user_id'] = uid
    respuesta = client.get('/form-pruebas/gestion/por-rendir')
    assert respuesta.status_code == 200
    assert respuesta.text.index('Luis Prueba') < respuesta.text.index('Ana Prueba')
    assert 'DEP-p1' in respuesta.text and 'DEP-p2' in respuesta.text
    assert 'DEP-p3' not in respuesta.text and 'DEP-FUERA' not in respuesta.text
    assert fuente(portal) == antes


def test_clave_inicial_obliga_a_cambiarla_y_vence_al_mes(portal):
    from datetime import datetime, timedelta
    from models import ClaveTecnico
    client = portal.test_client()
    r = entrar(client, '00004444')
    assert r.status_code == 200 and r.json['debe_cambiar'] is True
    assert b'id="form-clave"' in client.get('/form-pruebas/').data
    assert client.get('/form-pruebas/datos').status_code == 403  # solo puede cambiar la clave
    for cuerpo, error in (({'actual': 'x', 'nueva': 'abc12345', 'confirmar': 'abc12345'}, 'actual'),
                          ({'actual': '00004444', 'nueva': 'abc', 'confirmar': 'abc'}, '6'),
                          ({'actual': '00004444', 'nueva': 'abc12345', 'confirmar': 'otra123'}, 'confirmación'),
                          ({'actual': '00004444', 'nueva': '00004444', 'confirmar': '00004444'}, 'documento')):
        r = client.post('/form-pruebas/clave', json=cuerpo, headers=headers(client))
        assert r.status_code == 400 and error in r.json['error'], r.json
    r = client.post('/form-pruebas/clave', json={'actual': '00004444', 'nueva': 'Segura-2026', 'confirmar': 'Segura-2026'},
                    headers=headers(client))
    assert r.status_code == 200, r.json
    assert client.get('/form-pruebas/datos').status_code == 200
    # El DNI ya no sirve; la nueva clave sí y no pide cambio
    otro = portal.test_client()
    assert entrar(otro, '00004444').status_code == 401
    r = entrar(otro, '00004444', 'Segura-2026')
    assert r.status_code == 200 and r.json['debe_cambiar'] is False
    # Pasados 30 días vuelve a exigir el cambio
    with portal.app_context():
        registro = db.session.get(ClaveTecnico, '00004444')
        registro.cambiada_en = datetime.utcnow() - timedelta(days=31); db.session.commit()
    r = entrar(portal.test_client(), '00004444', 'Segura-2026')
    assert r.json['debe_cambiar'] is True


def test_restablecer_vuelve_al_documento(portal):
    from services import claves_tecnico
    client = portal.test_client()
    assert entrar(client, '00001111', 'no-es').status_code == 401
    with portal.app_context():
        claves_tecnico.cambiar('00001111', 'Otra-clave-1')
        claves_tecnico.restablecer('00001111'); db.session.commit()
    r = entrar(portal.test_client(), '00001111')
    assert r.status_code == 200 and r.json['debe_cambiar'] is True


def test_muchos_ingresos_seguidos_no_se_bloquean_entre_si(portal):
    """Varios técnicos desde la misma IP: solo se frena al documento con claves erradas."""
    for _ in range(12):  # 12 ingresos correctos seguidos desde la misma IP
        with portal.test_client() as client:
            assert entrar(client).status_code == 200
    with portal.test_client() as client:
        for _ in range(8):
            assert entrar(client, '00002222', 'clave-mala').status_code == 401
        assert entrar(client, '00002222').status_code == 429  # Luis espera un minuto
        assert entrar(client, '00001111').status_code == 200  # Ana entra igual
