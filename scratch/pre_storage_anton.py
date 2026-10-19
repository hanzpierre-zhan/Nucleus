import json,sys,hashlib,os,subprocess,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path.cwd()))
from scripts.conciliar_cotizaciones_anton import generar
p=Path('backups/migracion-anton-final-20261018');q=Path('backups/preparacion-anton-20261018')
def cfg(name):return json.loads((q/'accesos-anton-actual.json' if name=='anton' else Path('backups/migracion-modus-20261018/accesos-nucleus.json')).read_text())
def inventory(name):
 c=cfg(name);s=boto3.client('s3',endpoint_url=c['B2_ENDPOINT_URL'],aws_access_key_id=c['B2_KEY_ID'],aws_secret_access_key=c['B2_APP_KEY'],region_name=c['B2_REGION'],config=Config(connect_timeout=15,read_timeout=60,retries={'max_attempts':2}))
 a={o['Key']:{'bytes':o['Size'],'etag':o['ETag']} for page in s.get_paginator('list_objects_v2').paginate(Bucket=c['B2_BUCKET']) for o in page.get('Contents',[])}
 (p/('inventario_'+name+'.json')).write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8');return a
def native():
 u=make_url(cfg('nucleus')['DATABASE_URL']);env=os.environ.copy();env.update(PGHOST=u.host,PGPORT=str(u.port or 5432),PGDATABASE=u.database,PGUSER=u.username,PGPASSWORD=u.password,PGSSLMODE='require',PGCONNECT_TIMEOUT='15');b=Path('scratch/postgres-tools/pgsql/bin').resolve();f=(p/'nucleus_pre_final.dump').resolve()
 if f.exists():return
 r=subprocess.run([str(b/'pg_dump.exe'),'-Fc','--no-password','--file',str(f)],env=env,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
 if r.returncode:(p/'dump_error_privado.txt').write_bytes(r.stderr);raise RuntimeError('Respaldo nativo falló')
 r=subprocess.run([str(b/'pg_restore.exe'),'--list',str(f)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW);assert r.returncode==0
 (p/'dump_manifest.json').write_text(json.dumps({'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'indice_verificado':True}),encoding='utf-8');print('RESPALDO_NATIVO_OK',flush=True)
try:
 with ThreadPoolExecutor(max_workers=3) as pool:
  a=pool.submit(inventory,'anton');n=pool.submit(inventory,'nucleus');b=pool.submit(native);a,n=a.result(),n.result();b.result()
 old=json.loads((q/'respaldo_b2_anton_actual.manifest.json').read_text(encoding='utf-8'))['objetos']
 assert len(a)==len(old) and all(a[o['clave']]=={'bytes':o['bytes'],'etag':o['etag']} for o in old),'B2 Anton cambió: renovar respaldo'
 numeracion=generar(p/'anton_pre_final.db',p/'nucleus_pre_final.db',renumerar_px=True)['numeracion']
 folders={o['original']:o['numero_px'] for k,o in numeracion.items() if k.startswith('nucleus_data:')}
 plan=[];mapping={};reserved=set(n)
 for o in old:
  key=o['clave'];root,sep,tail=key.partition('/');dest=(folders[root]+'/'+tail) if sep and root in folders else key
  f=q/o['archivo_local'];data=f.read_bytes();assert hashlib.sha256(data).hexdigest()==o['sha256'];md5=hashlib.md5(data).hexdigest()
  actual=n.get(dest)
  if actual and (actual['bytes']!=len(data) or actual['etag'].strip('"')!=md5):
   folder,sep,filename=dest.rpartition('/');stem,dot,ext=filename.rpartition('.')
   stem=stem if dot else filename;ext='.'+ext if dot else '';dest=(folder+'/' if sep else '')+stem+'_anton_'+o['sha256'][:12]+ext
  actual=n.get(dest)
  if actual:assert actual['bytes']==len(data) and actual['etag'].strip('"')==md5,'Colisión de destino'
  assert dest not in {r['destino'] for r in plan},'Destino duplicado'
  if key!=dest:mapping[key]=dest
  plan.append({**o,'destino':dest,'md5':md5,'subir':actual is None,'archivo_absoluto':str(f.resolve())})
 (p/'plan_archivos.json').write_text(json.dumps({'objetos':plan,'mapa':mapping,'numeracion':numeracion},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'archivos':len(plan),'subir':sum(o['subir'] for o in plan),'rutas_diferenciadas':len(mapping)}),flush=True)
except Exception:
 (p/'pre_storage_error.txt').write_text(traceback.format_exc(),encoding='utf-8');print('ERROR_PRIVADO');sys.exit(1)
