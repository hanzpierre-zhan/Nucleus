import json,sys,sqlite3,traceback
from pathlib import Path
from sqlalchemy import create_engine,MetaData,select,text
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path.cwd()))
from scripts.migrar_modus import importar
from scripts.plan_migracion_modus import construir,aplicar,serializar
p=Path('backups/migracion-modus-20261018');cfg=json.loads((p/'accesos-nucleus.json').read_text());u=make_url(cfg['DATABASE_URL']).set(drivername='postgresql+psycopg2').update_query_dict({'connect_timeout':'15'});remote=create_engine(u,hide_parameters=True)
base=p/'nucleus_inmediato_pre_carga.db';trial=p/'ensayo_inmediato_pre_carga.db'
for f in [base,trial]:
 with f.open('xb'):pass
baseline=create_engine('sqlite:///'+base.resolve().as_posix());ensayo=create_engine('sqlite:///'+trial.resolve().as_posix());source=create_engine('sqlite:///'+(p/'modus_pre_carga_20261018.db').resolve().as_posix())
try:
 assert json.loads((p/'transferencia_b2_verificada.json').read_text())['total']==34
 with remote.begin() as conn:
  conn.execute(text("SET LOCAL lock_timeout='15s'"));conn.execute(text('SELECT pg_advisory_xact_lock(740182026)'))
  m=MetaData();m.reflect(bind=conn)
  names=','.join(conn.dialect.identifier_preparer.quote(n) for n in m.tables)
  conn.exec_driver_sql('LOCK TABLE '+names+' IN SHARE ROW EXCLUSIVE MODE')
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
  resultado_ensayo=importar(source,ensayo)
  plan=construir(baseline,ensayo)
  (p/'plan_final_privado.json').write_text(json.dumps(plan,default=serializar,ensure_ascii=False,indent=2),encoding='utf-8')
  resultado=aplicar(plan,remote,conexion=conn)
  counts={t:conn.scalar(text('SELECT count(*) FROM '+t)) for t in ['nucleus_data','usuarios','historial_cambios','migracion_modus_origen']}
 (p/'carga_produccion_verificada.json').write_text(json.dumps({'resultado':resultado,'conteos':counts,'ensayo':resultado_ensayo},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':True,'conteos':counts,'registros_importados':resultado['nucleus_data']['insertados'],'personal_conservado':resultado_ensayo.get('nucleus_data:personal_nucleus_conservado')}))
except Exception as ex:
 (p/'carga_atomica_error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8');print(json.dumps({'ok':False,'tipo_error':type(ex).__name__,'motivo':str(ex) if isinstance(ex,ValueError) else 'Diagnostico guardado; transaccion revertida'}));sys.exit(1)
finally:
 remote.dispose();baseline.dispose();ensayo.dispose();source.dispose()
