from app import create_app
from db import db
from models import Proyecto, AppConfig, NucleusData
import json

app = create_app()

with app.app_context():
    # 1. Rename Proyecto
    proy = Proyecto.query.filter_by(nombre='FLM (old)').first()
    if proy:
        proy.nombre = 'FLM - ENTEL'
        print("Proyecto renombrado a FLM - ENTEL")
    else:
        # Check if it was already renamed
        proy = Proyecto.query.filter_by(nombre='FLM - ENTEL').first()
        if proy:
            print("Proyecto ya se llamaba FLM - ENTEL")
        else:
            print("Proyecto no encontrado.")
            exit()
    
    # 2. Update app_schema
    schema_config = AppConfig.query.filter_by(proyecto_id=proy.id, clave='app_schema').first()
    if schema_config and schema_config.valor:
        schema = json.loads(schema_config.valor)
        # Remove SLA and SLA CUMPLIMIENTO
        schema = [col for col in schema if col not in ('SLA', 'SLA CUMPLIMIENTO')]
        schema_config.valor = json.dumps(schema, ensure_ascii=False)
        print("Columnas quitadas de app_schema")

    # 3. Update all data JSONs
    rows = NucleusData.query.filter_by(proyecto_id=proy.id).all()
    count = 0
    for row in rows:
        d = json.loads(row.data_json)
        changed = False
        if 'SLA' in d:
            del d['SLA']
            changed = True
        if 'SLA CUMPLIMIENTO' in d:
            del d['SLA CUMPLIMIENTO']
            changed = True
            
        if changed:
            row.data_json = json.dumps(d, ensure_ascii=False)
            count += 1
            
    db.session.commit()
    print(f"Borradas las columnas de {count} filas")
