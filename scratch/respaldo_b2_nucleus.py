import json,hashlib,concurrent.futures,sys
from pathlib import Path
import boto3
from botocore.config import Config
p=Path('backups/migracion-modus-20261018');c=json.loads((p/'accesos-nucleus.json').read_text());inv=json.loads((p/'inventario_b2_nucleus_20261018.json').read_text(encoding='utf-8'));out=p/'b2_nucleus_objetos';out.mkdir(exist_ok=True)
s=boto3.client('s3',endpoint_url=c['B2_ENDPOINT_URL'],aws_access_key_id=c['B2_KEY_ID'],aws_secret_access_key=c['B2_APP_KEY'],region_name=c['B2_REGION'],config=Config(connect_timeout=15,read_timeout=60,max_pool_connections=8,retries={'max_attempts':3}))
def descargar(o):
 f=out/(hashlib.sha256(o['clave'].encode()).hexdigest()+'.bin')
 r=s.get_object(Bucket=c['B2_BUCKET'],Key=o['clave'],IfMatch=o['etag'])
 h=hashlib.sha256();n=0
 with f.open('wb') as dst:
  for b in r['Body'].iter_chunks(1024*1024):dst.write(b);h.update(b);n+=len(b)
 r['Body'].close()
 if n!=o['bytes']:raise ValueError('tamano')
 return dict(o,archivo=f.name,sha256=h.hexdigest())
try:
 result=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for i,o in enumerate(pool.map(descargar,inv['objetos']),1):
   result.append(o)
   if i%500==0:print(json.dumps({'descargados':i,'total':len(inv['objetos'])}),flush=True)
 manifest={'sistema':'Nucleus','objetos':result,'cantidad':len(result),'bytes':sum(o['bytes'] for o in result),'alcance':'objetos actuales; no versiones historicas'}
 (p/'respaldo_b2_nucleus_20261018.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'ok':True,'objetos':len(result),'bytes':manifest['bytes']}))
except Exception as e:print(json.dumps({'ok':False,'tipo_error':type(e).__name__}));sys.exit(1)
