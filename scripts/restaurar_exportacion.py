"""Restaura el ZIP administrativo de producción en un SQLite nuevo de pruebas.

Conserva los IDs originales y verifica cada conteo del manifiesto. No ejecuta
la app ni migraciones y no mezcla respaldos históricos con producción.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

from sqlalchemy import create_engine, DateTime, select, func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import db
import models  # noqa: F401: registra el esquema sin iniciar la aplicación


def restaurar(archivo, destino):
    destino=Path(destino).resolve()
    with destino.open('xb'):
        pass
    engine=create_engine('sqlite:///'+destino.as_posix())
    db.metadata.create_all(engine)
    informe={'origen':'exportacion administrativa de Nucleus publicado',
             'tablas':{},'adjuntos_descargados':False,
             'limite':'El ZIP no exporta token_store, conformidades, notificaciones ni tablas derivadas de liquidaciones.'}
    try:
        with zipfile.ZipFile(archivo) as z:
            manifest=json.loads(z.read('manifest.json'))
            if not isinstance(manifest.get('tablas'),dict):raise ValueError('Manifiesto inválido')
            contenido={t:[] for t in manifest['tablas']}
            for nombre in z.namelist():
                if nombre=='manifest.json':continue
                tabla=next((t for t in contenido if re.fullmatch(re.escape(t)+r'(?:_p\d+)?\.json',nombre)),None)
                if tabla is None:raise ValueError('Archivo inesperado en exportación')
                filas=json.loads(z.read(nombre))
                if not isinstance(filas,list) or any(not isinstance(f,dict) for f in filas):raise ValueError('Formato de filas inválido')
                contenido[tabla].extend(filas)
            with engine.begin() as con:
                for tabla in db.metadata.sorted_tables:
                    if tabla.name not in contenido:continue
                    filas=contenido[tabla.name]
                    if len(filas)!=manifest['tablas'][tabla.name]:raise ValueError('Conteo fuente no coincide: '+tabla.name)
                    columnas=set(tabla.columns.keys())
                    for fila in filas:
                        if set(fila)-columnas:raise ValueError('Hay columnas nuevas sin soporte: '+tabla.name)
                        for col in tabla.columns:
                            if isinstance(col.type,DateTime) and isinstance(fila.get(col.name),str):
                                fila[col.name]=datetime.fromisoformat(fila[col.name])
                    for inicio in range(0,len(filas),1000):
                        con.execute(tabla.insert(),filas[inicio:inicio+1000])
                    total=con.scalar(select(func.count()).select_from(tabla))
                    if total!=manifest['tablas'][tabla.name]:raise ValueError('Conteo destino no coincide: '+tabla.name)
                    informe['tablas'][tabla.name]=total
                if set(contenido)-set(informe['tablas']):raise ValueError('Hay tablas sin restaurar')
                if con.exec_driver_sql('PRAGMA foreign_key_check').fetchone():raise ValueError('Existen relaciones sin destino')
                if con.exec_driver_sql('PRAGMA integrity_check').scalar()!='ok':raise ValueError('Falló integridad')
            informe['exportado_en']=manifest.get('exportado_en')
            informe['proyecto_por_id']=manifest.get('proyecto_por_id')
    finally:
        engine.dispose()
    with destino.open('rb') as f:informe['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    destino.with_suffix('.manifest.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
    return informe


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--zip',required=True);p.add_argument('--destino',required=True)
    a=p.parse_args();r=restaurar(a.zip,a.destino)
    print('Exportación verificada:',r['tablas'].get('nucleus_data',0),'registros;',r['tablas'].get('usuarios',0),'usuarios')
