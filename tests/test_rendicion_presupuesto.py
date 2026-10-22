import json
from services.rendicion_presupuesto import presupuesto, corregir_fila


def test_nombres_canonicos_y_campos_ajenos():
    for raw, expected in [('COSTO COBRA','GASTO COBRA'),('Gasto Cobra','GASTO COBRA'),('REFRACTURABLE','REFACTURABLE'),(' refacturable ','REFACTURABLE')]:
        assert presupuesto(raw) == expected
    data={'Tipo de presupuesto':'COSTO COBRA','Tipo de gasto':'COSTO COBRA','ESTADO':'DEPOSITADO','MONTO PAGO':'10'}
    assert corregir_fila(data)
    assert data == {'Tipo de presupuesto':'GASTO COBRA','Tipo de gasto':'COSTO COBRA','ESTADO':'DEPOSITADO','MONTO PAGO':'10'}
    assert not corregir_fila(data)
    assert presupuesto('OTRO PRESUPUESTO') == 'OTRO PRESUPUESTO'


def test_corrige_historicos_opciones_y_nuevas_escrituras(app):
    from db import db
    from models import Proyecto, NucleusData, AppConfig
    from migrations import _migrar_rendicion
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Rendicion').one().id
        other=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        # Inserción directa representa registros anteriores al despliegue.
        for n, raw in enumerate(['COSTO COBRA','REFRACTURABLE']):
            db.session.execute(NucleusData.__table__.insert().values(proyecto_id=pid,key_value='PRES-HIST-'+str(n),data_json=json.dumps({'Tipo de presupuesto':raw,'ESTADO':'DEPOSITADO','MONTO PAGO':'25'})))
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='manual_columns').first()
        columns=[{'nombre':'Tipo de presupuesto','tipo':'lista','opciones':['COSTO COBRA','GASTO COBRA','REFRACTURABLE','REFACTURABLE']}]
        if cfg:
            db.session.execute(AppConfig.__table__.update().where(AppConfig.id==cfg.id).values(valor=json.dumps(columns)))
        else:
            db.session.execute(AppConfig.__table__.insert().values(proyecto_id=pid,clave='manual_columns',valor=json.dumps(columns)))
        db.session.commit();db.session.expire_all()
        _migrar_rendicion(Proyecto,AppConfig,NucleusData)
        for n, expected in enumerate(['GASTO COBRA','REFACTURABLE']):
            data=json.loads(NucleusData.query.filter_by(proyecto_id=pid,key_value='PRES-HIST-'+str(n)).one().data_json)
            assert data == {'Tipo de presupuesto':expected,'ESTADO':'DEPOSITADO','MONTO PAGO':'25'}
        options=json.loads(AppConfig.query.filter_by(proyecto_id=pid,clave='manual_columns').one().valor)
        assert options[0]['opciones'] == ['GASTO COBRA','REFACTURABLE']
        fresh=NucleusData(proyecto_id=pid,key_value='PRES-NUEVO',data_json=json.dumps({'Tipo de presupuesto':'REFRACTURABLE'}))
        unrelated=NucleusData(proyecto_id=other,key_value='PRES-AJENO',data_json=json.dumps({'Tipo de presupuesto':'COSTO COBRA'}))
        db.session.add_all([fresh,unrelated]);db.session.commit()
        assert json.loads(fresh.data_json)['Tipo de presupuesto']=='REFACTURABLE'
        assert json.loads(unrelated.data_json)['Tipo de presupuesto']=='COSTO COBRA'
        fresh.data_json=json.dumps({'Tipo de presupuesto':'COSTO COBRA'})
        db.session.commit()
        assert json.loads(fresh.data_json)['Tipo de presupuesto']=='GASTO COBRA'
