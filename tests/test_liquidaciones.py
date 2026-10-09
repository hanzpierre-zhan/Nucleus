import json
import pytest
from db import db
from models import Proyecto, NucleusData, RefacturableDetalle

@pytest.fixture
def liquidacion(app):
    with app.app_context():
        cot = Proyecto.query.filter_by(nombre='Cotizaciones').one()
        flm = Proyecto.query.filter_by(nombre='FLM - CLARO').one()
        wo = NucleusData(proyecto_id=flm.id, key_value='LIQ-WO-TEST', data_json=json.dumps({'ESTADO DE EJECUCION':'Culminado','_EVIDENCIA_INICIO':json.dumps(['/static/inicio.jpg']),'_BITACORA_INICIO':'Trabajo iniciado'}))
        fila = NucleusData(proyecto_id=cot.id, key_value='LIQ-COT-TEST',data_json=json.dumps({'ESTADO COTIZACION':'Atendido','SOLICITADO POR':'solicitante','GESTOR':'otro','NUMERO WO':'LIQ-WO-TEST','SUB TOTAL + FEE':'210.00','SUBTOTAL FACTURA PROVEEDOR':'120.50','GENERADA':'1','FECHA INICIO OBRA':'2026-10-01','FECHA FIN OBRA':'2026-10-09','ADJUNTO FACTURA PROVEEDOR':'/api/cotizacion/correo/1/test/factura.pdf','ADJUNTO CORREO CLIENTE':'/api/cotizacion/correo/1/test/correo.msg'}))
        db.session.add_all([wo,fila]);db.session.commit();ids=(fila.id,wo.id)
    yield ids[0]
    with app.app_context():
        RefacturableDetalle.query.filter_by(origen_id=ids[0]).delete()
        NucleusData.query.filter(NucleusData.id.in_(ids)).delete(synchronize_session=False);db.session.commit()


def obtener(client, id):
    r=client.get('/liquidaciones/api/registros');assert r.status_code==200
    return next(row for row in r.json['registros'] if row['id']==id)


def test_liquidacion_fuentes_documentos_y_avance(app,auth_client,liquidacion):
    row=obtener(auth_client,liquidacion)
    assert row['gestor']=='solicitante'
    assert row['nombre_proyecto']=='CLARO'
    assert row['estatus']=='Culminado'
    assert row['fecha_inicio']=='2026-10-01' and row['fecha_fin']=='2026-10-09'
    assert row['monto_hw']=='210.00' and row['monto_factura_proveedor']=='120.50'
    assert row['avance']==100
    assert row['fotos']['inicio']==['/static/inicio.jpg']
    assert row['comentarios']['inicio']=='Trabajo iniciado'
    with app.app_context():
        fila=db.session.get(NucleusData,liquidacion);d=json.loads(fila.data_json);d.pop('ADJUNTO FACTURA PROVEEDOR');fila.data_json=json.dumps(d);db.session.commit()
    assert obtener(auth_client,liquidacion)['avance']==75
    r=auth_client.patch('/liquidaciones/api/registros/%s'%liquidacion,json={'no_aplica_factura':'1','codigo_ajb_ejb':'AJB-123','mes_cierre':'2026-10','estado_liquidacion':'En revisión'})
    assert r.status_code==200
    assert r.json['registro']['avance']==100
    assert r.json['registro']['documentos']['factura']=='No aplica'
    assert r.json['registro']['codigo_ajb_ejb']=='AJB-123'
    assert r.json['registro']['correlativo']==row['correlativo']

@pytest.mark.parametrize('cambios',[{'fecha_inicio':'2026-10-01'},{'fecha_fin':'2026-10-09'},{'estatus':'Culminado'},{'no_aplica_factura':'si'},{'estado_liquidacion':'inventado'},{'mes_cierre':'2026-13'}])
def test_liquidaciones_rechaza_edicion_derivada_o_invalida(auth_client,liquidacion,cambios):
    assert auth_client.patch('/liquidaciones/api/registros/%s'%liquidacion,json=cambios).status_code==400


def test_fechas_en_sustento_validacion_y_persistencia(app,auth_client,liquidacion):
    bad=auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'LIQ-COT-TEST','fecha_inicio':'2026-10-09','fecha_fin':'2026-10-01'})
    assert bad.status_code==400
    good=auth_client.post('/api/cotizacion/sustento/guardar',json={'key':'LIQ-COT-TEST','fecha_inicio':'2026-10-02','fecha_fin':'2026-10-08','bitacoras':{'cierre':'Obra concluida'}})
    assert good.status_code==200,good.json
    row=obtener(auth_client,liquidacion)
    assert row['fecha_inicio']=='2026-10-02' and row['fecha_fin']=='2026-10-08'
    assert 'Obra concluida' in row['comentarios']['cierre']


def test_nombre_liquidaciones_y_compatibilidad(auth_client):
    for ruta in ('/liquidaciones/','/refacturable/'):
        r=auth_client.get(ruta);assert r.status_code==200
        assert b'Liquidaciones' in r.data and b'name="codigo_ajb_ejb"' in r.data


def test_descarga_cotizacion_generada(auth_client, liquidacion):
    response=auth_client.get('/liquidaciones/api/registros/%s/pdf'%liquidacion)
    assert response.status_code==200
    assert response.mimetype=='application/pdf'
    assert response.data.startswith(b'%PDF')
