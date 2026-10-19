import os,json,sys,subprocess,traceback
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from scripts.plan_migracion_modus import aplicar
p=Path('backups/migracion-anton-final-20261018').resolve();b=Path('scratch/postgres-tools/pgsql/bin').resolve();data=Path('scratch/postgres-tools/ensayo-data').resolve();pw=Path('backups/migracion-modus-20261018/postgres_ensayo_password.txt').read_text();env=os.environ.copy();env.update(PGHOST='127.0.0.1',PGPORT='55438',PGUSER='migration_test',PGPASSWORD=pw,PGDATABASE='postgres',PGCONNECT_TIMEOUT='10')
def run(args):
 with (p/'pg_ensayo_privado.log').open('ab') as output:r=subprocess.run([str(b/args[0]),*args[1:]],env=env,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
 if r.returncode:raise RuntimeError(args[0]+' falló')
try:
 run(['pg_ctl.exe','-D',str(data),'-l',str(p/'pg_server.log'),'-o','-p 55438 -h 127.0.0.1','-w','start'])
 try:
  run(['pg_restore.exe','--clean','--if-exists','--exit-on-error','--no-owner','--no-privileges','-d','anton_final',str(p/'nucleus_pre_final.dump')])
  e=create_engine(URL.create('postgresql+psycopg2',username='migration_test',password=pw,host='127.0.0.1',port=55438,database='anton_final'),hide_parameters=True)
  plan=json.loads((p/'plan_ensayo.json').read_text(encoding='utf-8'));r=aplicar(plan,e);e.dispose();(p/'ensayo_postgresql_ok.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print('RESTAURACION_Y_MIGRACION_POSTGRESQL_OK',flush=True)
 finally:run(['pg_ctl.exe','-D',str(data),'-m','fast','-w','stop'])
except Exception:
 (p/'pg_ensayo_error.txt').write_text(traceback.format_exc(),encoding='utf-8');print('ERROR_PRIVADO');sys.exit(1)
