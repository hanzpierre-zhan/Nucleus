import json,sys,sqlite3,traceback,xml.etree.ElementTree as ET
from pathlib import Path
from sqlalchemy import create_engine,MetaData,select,text
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path.cwd()))
from scripts.migrar_anton import importar
from scripts.plan_migracion_modus import construir,aplicar,serializar,filas,hash_filas
p=Path('backups/migracion-anton-final-20261018');cfg=json.loads(Path('backups/migracion-modus-20261018/accesos-nucleus.json').read_text());u=make_url(cfg['DATABASE_URL']).set(drivername='postgresql+psycopg2').update_query_dict({'connect_timeout':'15'});remote=create_engine(u,hide_parameters=True)
base=p/'nucleus_corte_atomico.db';trial=p/'ensayo_corte_atomico.db';eng=lambda f:create_engine('sqlite:///'+f.resolve().as_posix());baseline=eng(base);ensayo=eng(trial);source=eng(p/'anton_pre_final.db')
try:
 storage=json.loads((p/'plan_archivos.json').read_text(encoding='utf-8'));transfer=json.loads((p/'transferencia_verificada.json').read_text(encoding='utf-8'));assert transfer['total']==len(storage['objetos'])
 assert (p/'ensayo_postgresql_ok.json').exists() and (p/'ensayo_ui_ok.json').exists()
 suite=ET.parse(p/'pruebas_finales.xml').getroot().find('testsuite');assert int(suite.get('tests'))>=389 and suite.get('failures')=='0' and suite.get('errors')=='0'
 for f in [base,trial]:
  with f.open('xb'):pass
 with remote.begin() as conn:
  conn.execute(text("SET LOCAL lock_timeout='15s'"));conn.execute(text('SELECT pg_advisory_xact_lock(740182026)'))
  m=MetaData();m.reflect(bind=conn);names=','.join(conn.dialect.identifier_preparer.quote(n) for n in m.tables);conn.exec_driver_sql('LOCK TABLE '+names+' IN SHARE ROW EXCLUSIVE MODE')
  local=MetaData()
  for t in m.sorted_tables:
   clone=t.to_metadata(local)
   for col in clone.columns:col.type=col.type.as_generic();col.server_default=None;col.identity=None
   clone.indexes.clear()
  local.create_all(baseline)
  with baseline.begin() as dst:
   for t in m.sorted_tables:
    rows=conn.execute(select(t)).mappings()
    while batch:=rows.fetchmany(500):dst.execute(local.tables[t.name].insert(),[dict(r) for r in batch])
  baseline.dispose()
  with sqlite3.connect(base) as src,sqlite3.connect(trial) as dst:src.backup(dst)
  result=importar(source,ensayo,storage['mapa']);assert result['numeracion']==storage['numeracion'],'Numeración cambió: revisar antes de cargar'
  with sqlite3.connect(trial) as c:assert not c.execute('pragma foreign_key_check').fetchall()
  plan=construir(baseline,ensayo);(p/'plan_produccion_privado.json').write_text(json.dumps(plan,default=serializar,ensure_ascii=False),encoding='utf-8');applied=aplicar(plan,remote,conexion=conn)
  counts={t:conn.scalar(text('SELECT count(*) FROM '+t)) for t in ['nucleus_data','usuarios','historial_cambios','cotizaciones','migracion_anton_origen','migracion_anton_versiones']}
 (p/'commit_produccion.json').write_text(json.dumps({'conteos':counts,'carga':applied,'ensayo':result},ensure_ascii=False,indent=2),encoding='utf-8');print('COMMIT_PRODUCCION_REALIZADO',flush=True)
 with remote.connect() as conn:
  m=MetaData();m.reflect(conn)
  for n,spec in plan['tablas'].items():assert hash_filas(filas(conn,m.tables[n]))==spec['hash_despues'],n
 (p/'verificacion_postcommit.json').write_text(json.dumps({'verificado_en_conexion_independiente':True,'conteos':counts,'tablas':len(plan['tablas'])},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':True,'conteos':counts,'operativos_agregados':applied['nucleus_data']['insertados']}),flush=True)
except Exception as ex:
 (p/'carga_error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8');print(json.dumps({'ok':False,'tipo_error':type(ex).__name__,'motivo':str(ex) if isinstance(ex,ValueError) else 'Diagnóstico privado; comprobar marcador de commit'}));sys.exit(1)
finally:
 remote.dispose();baseline.dispose();ensayo.dispose();source.dispose()
