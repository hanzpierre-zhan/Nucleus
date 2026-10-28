"""Eliminar no puede borrar el estado y reimportar solicitudes anuladas."""
import io
import json
from db import db
from models import Proyecto,NucleusData,AppConfig


def test_eliminar_anulado_no_lo_reingresa_a_validacion(app,auth_client,monkeypatch):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        key='REGRESSION-ANULADO-20261028'
        original={'Marca temporal':key,'ESTADO':'ANULADO','MOTIVO RECHAZO':'Solicitud anulada','Nombre del proyecto':'Claro'}
        fila=NucleusData(proyecto_id=pid,key_value=key,data_json=json.dumps(original))
        db.session.add(fila)
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='rendicion_csv_url').first()
        previous=cfg.valor if cfg else None
        if cfg is None:
            cfg=AppConfig(proyecto_id=pid,clave='rendicion_csv_url');db.session.add(cfg)
        cfg.valor='https://example.test/regression.csv';db.session.commit()
    try:
        auth_client.get('/switch_project/'+str(pid))
        response=auth_client.post('/api/rows/delete',json={'keys':[key]})
        assert response.status_code==409
        assert 'volvería a importar' in response.json['error']
        csv='Marca temporal,Nombre del proyecto\n'+key+',Claro\n'
        monkeypatch.setattr('urllib.request.urlopen',lambda *a,**kw:io.BytesIO(csv.encode()))
        sync=auth_client.post('/api/rendicion/sync')
        assert sync.status_code==200 and sync.json['nuevas']==0
        with app.app_context():
            rows=NucleusData.query.filter_by(proyecto_id=pid,key_value=key).all()
            assert len(rows)==1
            data=json.loads(rows[0].data_json)
            assert data['ESTADO']=='ANULADO' and data['MOTIVO RECHAZO']=='Solicitud anulada'
    finally:
        with app.app_context():
            NucleusData.query.filter_by(proyecto_id=pid,key_value=key).delete()
            cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='rendicion_csv_url').one()
            if previous is None:db.session.delete(cfg)
            else:cfg.valor=previous
            db.session.commit()
