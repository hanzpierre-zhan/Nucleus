"""Retira las dos columnas calculadas antiguas sin tocar fechas ni estados de WO."""
import json,re,unicodedata
from functools import lru_cache
from sqlalchemy import event
from db import db
from models import AppConfig,NucleusData

def retired(field):
    return _retired_name(str(field or ''))

@lru_cache(maxsize=512)
def _retired_name(field):
    text=unicodedata.normalize('NFKD',field).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]','',text) in ('sla','slacumplimiento')

def clean_config(key,value):
    if key not in ('manual_columns','app_schema','column_layout') and not key.startswith('column_layout__'):return value
    try:items=json.loads(value)
    except (ValueError,TypeError):return value
    if not isinstance(items,list):return value
    cleaned=[item for item in items if not retired((item.get('nombre') or item.get('field')) if isinstance(item,dict) else item)]
    return json.dumps(cleaned,ensure_ascii=False) if len(cleaned)!=len(items) else value

def install():
    if getattr(install,'ready',False):return
    @event.listens_for(db.session,'before_flush')
    def clean_writes(session,*args):
        for row in list(session.new)+list(session.dirty):
            if isinstance(row,AppConfig):row.valor=clean_config(row.clave,row.valor)
            elif isinstance(row,NucleusData):
                try:data=json.loads(row.data_json or '{}')
                except (ValueError,TypeError):continue
                if isinstance(data,dict) and any(retired(k) for k in data):
                    row.data_json=json.dumps({k:v for k,v in data.items() if not retired(k)},ensure_ascii=False)
    install.ready=True

def clean_existing_config():
    for row in AppConfig.query.all():
        value=clean_config(row.clave,row.valor)
        if value!=row.valor:row.valor=value
    db.session.commit()
