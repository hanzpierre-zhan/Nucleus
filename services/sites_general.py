"""Reemplazo único y transaccional del maestro, versionado con el despliegue."""
import json
import re
from pathlib import Path
from collections import defaultdict
from db import db
from models import Proyecto, NucleusData, AppConfig, TokenStore
from flask import current_app

VERSION = 'sites_general_20261023_v1'
BACKUP = 'sites_antes_general_20261023'
KEYS = ['Site','Nombre','Código','Dirección','Tipo de Site','Distrito','Provincia','Región','Latitud (°)','Longitud (°)','Contrata','PROYECTO']
EXCEL_KEYS = ['Site','Nombre del sitio | Site name','Código del sitio | Site ID','Ubicación del sitio | Site address','Tipo de site | Site type','Distrito | District','Provincia | Provincia','Region | Region','Latitud','Longitud','Contrata','Proyecto']

def columnas():
    return [{'nombre': k, 'tipo': 'lista' if k == 'Proyecto' else 'texto',
             'opciones': ['FLM - ENTEL','FLM - CLARO','FLM - INTEGRATEL','FLM - PEXT'] if k == 'Proyecto' else []} for k in EXCEL_KEYS]

def datos_excel(data):
    result={dest:data.get(dest,data.get(src,'')) for src,dest in zip(KEYS,EXCEL_KEYS)}
    if result['Proyecto'] in ('ENTEL','CLARO','INTEGRATEL','PEXT'):
        result['Proyecto']='FLM - '+result['Proyecto']
    result.update({k:v for k,v in data.items() if k not in KEYS and k not in EXCEL_KEYS})
    return result

def actualizar_postgres(connection,changes):
    from psycopg2.extras import execute_values
    with connection.cursor() as cursor:
        for offset in range(0,len(changes),500):
            batch=changes[offset:offset+500]
            execute_values(cursor,
                'UPDATE nucleus_data AS target SET data_json = source.data_json '
                'FROM (VALUES %s) AS source(id, data_json) WHERE target.id = source.id',
                batch,page_size=500)
            current_app.logger.warning('[startup] Sites actualizados: %d/%d',min(offset+500,len(changes)),len(changes))

def guardar_cambios_sites(changes):
    """Una ida a Postgres por lote, no una por cada uno de los 18 604 sites."""
    if not changes:return
    if db.engine.dialect.name=='postgresql':
        connection=db.session.connection().connection.driver_connection
        actualizar_postgres(connection,changes)
    else:
        db.session.execute(db.text('UPDATE nucleus_data SET data_json=:data WHERE id=:row_id'),
            [{'row_id':row_id,'data':data} for row_id,data in changes])

def respetar_columnas_excel():
    marker='sites_columnas_excel_v2'
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(917348262)'))
    if TokenStore.query.filter_by(clave=marker).first():return
    proyecto=Proyecto.query.filter_by(nombre='SITE').one()
    try:
        changes=[]
        rows=db.session.query(NucleusData.id,NucleusData.data_json).filter_by(proyecto_id=proyecto.id).all()
        for row_id,data_json in rows:
            d=json.loads(data_json)
            nuevo=datos_excel(d)
            updated=json.dumps(nuevo,ensure_ascii=False)
            if updated!=data_json:changes.append((row_id,updated))
        current_app.logger.warning('[startup] Migrando columnas de %d sites por lotes',len(changes))
        guardar_cambios_sites(changes)
        values={'manual_columns':json.dumps(columnas(),ensure_ascii=False),'app_schema':'[]',
                'column_layout':json.dumps([{'field':'_key' if k=='Site' else k,'visible':True} for k in EXCEL_KEYS],ensure_ascii=False)}
        backup={}
        for key,value in values.items():
            config=AppConfig.query.filter_by(proyecto_id=proyecto.id,clave=key).one()
            backup[key]=config.valor
            config.valor=value
        db.session.add(TokenStore(clave=marker,valor=json.dumps(backup,ensure_ascii=False)))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def cargar():
    source = json.loads((Path(__file__).resolve().parent.parent/'data/sites_general_20261023.json').read_text(encoding='utf-8'))
    rows = source['rows']
    keys = [r['Site'] for r in rows]
    if len(rows) != 18604 or len(set(keys)) != len(keys) or any(not k or len(k)>100 for k in keys):
        raise ValueError('El maestro Site General no supera la validación de integridad.')
    return source

def aplicar():
    # El lock transaccional también cubre arranques simultáneos tras un deploy.
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(917348262)'))
    if TokenStore.query.filter_by(clave=VERSION).first():
        return
    source = cargar()
    proyecto = Proyecto.query.filter_by(nombre='SITE').one()
    try:
        old = NucleusData.query.filter_by(proyecto_id=proyecto.id).all()
        configs = AppConfig.query.filter_by(proyecto_id=proyecto.id).all()
        backup = {'source':source['source'],'sha256':source['sha256'],
                  'rows':[{'id':r.id,'key':r.key_value,'data_json':r.data_json} for r in old],
                  'config':{r.clave:r.valor for r in configs},'cotizaciones':[]}
        # Conservar las filas originales en BD antes de sustituir el catálogo.
        NucleusData.query.filter_by(proyecto_id=proyecto.id).delete(synchronize_session=False)
        db.session.bulk_insert_mappings(NucleusData,[{'proyecto_id':proyecto.id,'key_value':r['Site'],
            'data_json':json.dumps(datos_excel(r),ensure_ascii=False)} for r in source['rows']])
        for key, value in {'primary_key':'Site','manual_columns':json.dumps(columnas(),ensure_ascii=False),
                           'app_schema':'[]','column_layout':'[]'}.items():
            config = next((r for r in configs if r.clave==key),None)
            if config:config.valor=value
            else:db.session.add(AppConfig(proyecto_id=proyecto.id,clave=key,valor=value))
        completar_fichas(source['rows'],backup['cotizaciones'])
        db.session.add(TokenStore(clave=BACKUP,valor=json.dumps(backup,ensure_ascii=False)))
        db.session.add(TokenStore(clave=VERSION,valor=json.dumps({'count':len(source['rows']),'sha256':source['sha256']})))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def completar_fichas(rows,backup):
    """Completa solo huecos con coincidencia única; conserva textos, fotos y WO."""
    from services.cotizacion_ficha import normalizar, usa_ficha
    from services.recursos_flm import familia
    index=defaultdict(list)
    def identidad(value):
        return normalizar(re.sub(r'^0+(?=\d)', '', str(value or '').strip()))
    mapping={'site_name':'Nombre','site_id':'Código','site_address':'Dirección','site_type':'Tipo de Site',
             'district':'Distrito','province':'Provincia','region':'Región'}
    for row in rows:
        for key in {identidad(row[k]) for k in ('Site','Nombre','Código')}:
            if key:index[(familia(row['PROYECTO']),key)].append(row)
    cot=Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not cot:return
    for registro in NucleusData.query.filter_by(proyecto_id=cot.id).yield_per(200):
        datos=json.loads(registro.data_json or '{}')
        if not usa_ficha(datos):continue
        original=registro.data_json
        for manual in datos.get('_SUSTENTO_FICHAS',{}).values():
            if not isinstance(manual,dict):continue
            candidates=[]
            for value in (manual.get('site_name'),datos.get('NOMBRE SITE'),manual.get('site_id')):
                if value:
                    candidates=index.get((familia(datos.get('CLIENTE')),identidad(value)),[])
                    if len(candidates)==1:break
            if len(candidates)!=1:continue
            for field,col in mapping.items():
                if not str(manual.get(field) or '').strip():manual[field]=candidates[0][col]
        updated=json.dumps(datos,ensure_ascii=False)
        if json.loads(original)!=datos:
            backup.append({'id':registro.id,'data_json':original})
            registro.data_json=updated

def completar_existentes():
    """Alineación adicional para identificadores históricos con ceros iniciales."""
    marker='fichas_sites_general_v1'
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(917348262)'))
    if TokenStore.query.filter_by(clave=marker).first():return
    try:
        backup=[]
        completar_fichas(cargar()['rows'],backup)
        db.session.add(TokenStore(clave=marker,valor=json.dumps({'cotizaciones':backup},ensure_ascii=False)))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
