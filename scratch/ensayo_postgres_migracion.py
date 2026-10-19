import os,json,secrets,subprocess,sys
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.engine import URL
sys.path.insert(0,str(Path.cwd()));from scripts.migrar_modus import importar
p=Path('backups/migracion-modus-20261018').resolve();b=Path('scratch/postgres-tools/pgsql/bin').resolve();data=Path('scratch/postgres-tools/ensayo-data').resolve();pwfile=p/'postgres_ensayo_password.txt';pw=pwfile.read_text(encoding='utf-8');env=os.environ.copy();env.update(PGHOST='127.0.0.1',PGPORT='55438',PGUSER='migration_test',PGPASSWORD=pw,PGDATABASE='postgres',PGCONNECT_TIMEOUT='10');log=p/'postgres_ensayo_comandos_privado.log'
def run(args):
 with log.open('ab') as output:
  r=subprocess.run([str(b/args[0]),*args[1:]],env=env,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
 if r.returncode:raise RuntimeError(args[0]+' fallo; diagnostico privado')
 return r
try:
 run(['pg_ctl.exe','-D',str(data),'-l',str(p/'postgres_ensayo_privado.log'),'-o','-p 55438 -h 127.0.0.1','-w','start'])
 url=URL.create('postgresql+psycopg2',username='migration_test',password=pw,host='127.0.0.1',port=55438,database='ensayo_nucleus')
 target=create_engine(url);baseline=create_engine(url.set(database='baseline_nucleus'));source=create_engine('sqlite:///'+(p/'modus_neon_20261018.db').as_posix());result=json.loads((p/'ensayo_importacion_modus.resultado.json').read_text());repeat=importar(source,target)
 with target.connect() as c:
  counts={t:c.scalar(text('select count(*) from '+t)) for t in ['nucleus_data','usuarios','migracion_modus_origen']}
  fk=c.execute(text("select count(*) from refacturable_detalle r left join nucleus_data n on r.origen_id=n.id where n.id is null")).scalar()
 from scripts.plan_migracion_modus import construir,serializar,aplicar
 plan=construir(baseline,target)
 (p/'plan_produccion_privado.json').write_text(json.dumps(plan,default=serializar,ensure_ascii=False,indent=2),encoding='utf-8')
 resultado_lotes=aplicar(plan,baseline)
 assert fk==0
 (p/'ensayo_carga_lotes.json').write_text(json.dumps(resultado_lotes,indent=2),encoding='utf-8')
 (p/'ensayo_postgres_verificado.json').write_text(json.dumps({'restauracion_nativa':True,'primera_carga':result,'repeticion':repeat,'conteos':counts,'referencias_rotas':fk},indent=2),encoding='utf-8');print(json.dumps({'restauracion_nativa':True,'conteos':counts,'referencias_rotas':fk}))
 target.dispose();source.dispose()
finally:
 run(['pg_ctl.exe','-D',str(data),'-m','fast','-w','stop'])

