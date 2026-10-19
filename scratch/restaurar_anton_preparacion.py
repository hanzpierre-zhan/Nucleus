import os,json,subprocess,sys
from pathlib import Path
from sqlalchemy import create_engine,MetaData,select,func
from sqlalchemy.engine import URL
p=Path('backups/preparacion-anton-20261018').resolve();d=Path('backups/migracion-modus-20261018').resolve();b=Path('scratch/postgres-tools/pgsql/bin').resolve();data=Path('scratch/postgres-tools/ensayo-data').resolve();pw=(d/'postgres_ensayo_password.txt').read_text();env=os.environ.copy();env.update(PGHOST='127.0.0.1',PGPORT='55438',PGUSER='migration_test',PGPASSWORD=pw,PGDATABASE='postgres',PGCONNECT_TIMEOUT='10');log=p/'restauracion_comandos_privado.log'
def run(args):
 with log.open('ab') as output:r=subprocess.run([str(b/args[0]),*args[1:]],env=env,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
 if r.returncode:raise RuntimeError(args[0]+' fallo')
try:
 run(['pg_ctl.exe','-D',str(data),'-l',str(p/'postgres_anton_server.log'),'-o','-p 55438 -h 127.0.0.1','-w','start'])
 try:
  run(['pg_restore.exe','--clean','--if-exists','--exit-on-error','--no-owner','--no-privileges','-d','anton_preparacion',str(p/'anton_supabase_public_20261018.dump')])
  e=create_engine(URL.create('postgresql+psycopg2',username='migration_test',password=pw,host='127.0.0.1',port=55438,database='anton_preparacion'));m=MetaData();m.reflect(e)
  with e.connect() as conn:counts={t.name:conn.scalar(select(func.count()).select_from(t)) for t in m.sorted_tables}
  e.dispose();manifest=json.loads((p/'respaldo_nativo.manifest.json').read_text());manifest['restauracion_ensayada']=True;manifest['tablas_restauradas']=counts;(p/'respaldo_nativo.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps({'restauracion_nativa_verificada':True,'tablas':len(counts),'filas_operativas':counts['nucleus_data']}))
 finally:run(['pg_ctl.exe','-D',str(data),'-m','fast','-w','stop'])
except Exception as ex:print(json.dumps({'restauracion_nativa_verificada':False,'error':type(ex).__name__}));sys.exit(1)
