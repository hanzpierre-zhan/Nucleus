import io,json
from test_cotizacion_proveedor import cotizacion
from models import NucleusData
from db import db


def test_facturas_ocs_persisten_y_quitar_una_conserva_las_otras(app,auth_client,cotizacion):
    pid,key=cotizacion
    assert auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion'}).status_code==200
    urls={}
    for tipo in ('factura','oc'):
        urls[tipo]=[]
        for i in range(2):
            r=auth_client.post('/api/cotizacion/subir_'+tipo+'_proveedor',data={'key':key,'adjunto':(io.BytesIO(b'%PDF archivo '+str(i).encode()),tipo+str(i)+'.pdf')})
            assert r.status_code==200,r.json;urls[tipo].append(r.json['url'])
    r=auth_client.post('/api/cotizacion/proveedor',json={'key':key,'numero_factura':'F-1, F-2','numero_oc':'OC-1, OC-2','subtotal_factura':'100','facturas_proveedor':urls['factura'],'ocs_proveedor':urls['oc']})
    assert r.status_code==200,r.json
    # Un cliente antiguo no debe borrar los documentos adicionales.
    r=auth_client.post('/api/cotizacion/proveedor',json={'key':key,'numero_factura':'F-1, F-2','numero_oc':'OC-1, OC-2','subtotal_factura':'100','factura_proveedor':urls['factura'][0]})
    assert r.status_code==200,r.json
    assert r.json['newData']['_PROVEEDOR_FACTURAS']==urls['factura']
    assert r.json['newData']['_PROVEEDOR_OCS']==urls['oc']
    r=auth_client.post('/api/cotizacion/adjunto/eliminar',json={'key':key,'campo':'ADJUNTO FACTURA PROVEEDOR','url':urls['factura'][0]})
    assert r.status_code==200,r.json
    assert r.json['newData']['_PROVEEDOR_FACTURAS']==urls['factura'][1:]
    assert r.json['newData']['ADJUNTO FACTURA PROVEEDOR']==urls['factura'][1]
    for url in urls['oc']+urls['factura'][1:]:assert auth_client.get(url).status_code==200


def test_rechaza_adjuntos_de_otra_cotizacion(auth_client,cotizacion):
    pid,key=cotizacion
    auth_client.post('/api/cotizacion/accion',json={'key':key,'accion':'conformar_aprobacion'})
    r=auth_client.post('/api/cotizacion/proveedor',json={'key':key,'numero_factura':'F-1','numero_oc':'OC-1','subtotal_factura':'100','facturas_proveedor':['/api/cotizacion/correo/1/OTRA/factura_proveedor_x.pdf']})
    assert r.status_code==400
