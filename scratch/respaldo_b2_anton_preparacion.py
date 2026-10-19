import json,hashlib,concurrent.futures,sys
from pathlib import Path
import boto3
from botocore.config import Config
p=Path('backups/preparacion-anton-20261018');d=Path('backups/migracion-modus-20261018');c=json.loads((p/'accesos-anton-actual.json').read_text());src=json.loads((p/'inventario_b2_anton_actual.json').read_text(encoding='utf-8'))['objetos'];old=json.loads((d/'respaldo_b2_nucleus_20261018.manifest.json').read_text(encoding='utf-8'))['objetos'];idx={(o['clave'],o['bytes'],o['etag']):o for o in old};folder=p/'b2_anton_objetos';folder.mkdir(exist_ok=True);done=[];pending=[]
for o in src:
 cached=idx.get((o['clave'],o['bytes'],o['etag']))
 if cached:
  f=d/'b2_nucleus_objetos'/cached['archivo']
  with f.open('rb') as a:sha=hashlib.file_digest(a,'sha256').hexdigest()
  if f.stat().st_size!=o['bytes'] or sha!=cached['sha256']:raise ValueError('Respaldo reutilizable no coincide')
  done.append(dict(o,archivo_local='../migracion-modus-20261018/b2_nucleus_objetos/'+f.name,sha256=sha,reutilizado=True))
 else:pending.append(o)
print(json.dumps({'reutilizados_verificados':len(done),'por_descargar':len(pending)}),flush=True)
s=boto3.client('s3',endpoint_url=c['B2_ENDPOINT_URL'],aws_access_key_id=c['B2_KEY_ID'],aws_secret_access_key=c['B2_APP_KEY'],region_name=c['B2_REGION'],config=Config(connect_timeout=15,read_timeout=45,max_pool_connections=6,retries={'max_attempts':1}))
def download(o):
 f=folder/(hashlib.sha256(o['clave'].encode()).hexdigest()+'.bin');r=s.get_object(Bucket=c['B2_BUCKET'],Key=o['clave'],IfMatch=o['etag']);h=hashlib.sha256();size=0
 try:
  with f.open('wb') as dst:
   for chunk in r['Body'].iter_chunks(1024*1024):dst.write(chunk);h.update(chunk);size+=len(chunk)
 finally:r['Body'].close()
 if size!=o['bytes']:raise ValueError('Tamano diferente')
 return dict(o,archivo_local='b2_anton_objetos/'+f.name,sha256=h.hexdigest(),reutilizado=False)
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for start in range(0,len(pending),100):
   batch=list(pool.map(download,pending[start:start+100]));done.extend(batch)
   (p/'respaldo_b2_anton.parcial.json').write_text(json.dumps({'objetos':done,'faltan':len(src)-len(done)},ensure_ascii=False),encoding='utf-8');print(json.dumps({'respaldados':len(done),'total':len(src)}),flush=True)
 result={'sistema':'Anton','alcance':'objetos actuales; no versiones borradas; archivos existentes reutilizados por clave/tamano/ETag y SHA256 local','total':len(done),'bytes':sum(o['bytes'] for o in done),'reutilizados':sum(o['reutilizado'] for o in done),'descargados':sum(not o['reutilizado'] for o in done),'objetos':done}
 (p/'respaldo_b2_anton_actual.manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':True,'total':len(done),'descargados':result['descargados'],'reutilizados':result['reutilizados']}))
except Exception as ex:
 print(json.dumps({'ok':False,'error':type(ex).__name__,'completados':len(done)}));sys.exit(1)
