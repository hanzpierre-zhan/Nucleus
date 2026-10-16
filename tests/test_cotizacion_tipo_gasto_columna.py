import json
from flask import template_rendered
from db import db
from models import AppConfig, Proyecto


def test_tipo_gasto_existe_en_tabla_sin_esquema_actualizado(app, auth_client):
    with app.app_context():
        pid=Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='app_schema').first()
        previo=cfg.valor if cfg else None
        if not cfg:
            cfg=AppConfig(proyecto_id=pid,clave='app_schema');db.session.add(cfg)
        cfg.valor=json.dumps(['N° COTIZACION','CLIENTE'])
        db.session.commit()
    vistas=[]
    def capturar(sender,template,context,**extra):
        if template.name=='index.html': vistas.append(context)
    template_rendered.connect(capturar,app)
    try:
        response=auth_client.get(f'/switch_project/{pid}',follow_redirects=True)
        assert response.status_code==200
        assert 'TIPO DE GASTO' in json.loads(vistas[-1]['columns'])
        assert 'Gasto Cobra' in response.get_data(as_text=True)
    finally:
        template_rendered.disconnect(capturar,app)
        with app.app_context():
            cfg=AppConfig.query.filter_by(proyecto_id=pid,clave='app_schema').one()
            if previo is None: db.session.delete(cfg)
            else: cfg.valor=previo
            db.session.commit()
