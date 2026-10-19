import json,hashlib,mimetypes,concurrent.futures,base64,traceback,sys
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from urllib.parse import quote
import urllib.request
p=Path('backups/migracion-anton-final-20261018');c=json.loads(Path('backups/migracion-modus-20261018/accesos-nucleus.json').read_text());plan=json.loads((p/'plan_archivos.json').read_text(encoding='utf-8'));done=[]
s=boto3.client('s3',endpoint_url=c['B2_ENDPOINT_URL'],aws_access_key_id=c['B2_KEY_ID'],aws_secret_access_key=c['B2_APP_KEY'],region_name=c['B2_REGION'],config=Config(connect_timeout=15,read_timeout=60,retries={'max_attempts':2}))
def inventory():return {o['Key']:o for page in s.get_paginator('list_objects_v2').paginate(Bucket=c['B2_BUCKET']) for o in page.get('Contents',[])}
def transfer_once(o):
 data=Path(o['archivo_absoluto']).read_bytes();assert hashlib.sha256(data).hexdigest()==o['sha256'] and hashlib.md5(data).hexdigest()==o['md5']
 url=c['B2_ENDPOINT_URL'].rstrip('/')+'/'+quote(c['B2_BUCKET'],safe='')+'/'+quote(o['destino'],safe='/')
 req=AWSRequest(method='PUT',url=url,data=data,headers={'Content-Type':mimetypes.guess_type(o['destino'])[0] or 'application/octet-stream','x-amz-content-sha256':o['sha256'],'Content-MD5':base64.b64encode(hashlib.md5(data).digest()).decode()})
 SigV4Auth(Credentials(c['B2_KEY_ID'],c['B2_APP_KEY']),'s3',c['B2_REGION']).add_auth(req)
 with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=dict(req.headers),method='PUT'),timeout=60) as response:response.read()
 return o['destino']
def transfer(o):
 import time
 for attempt in range(5):
  try:return transfer_once(o)
  except Exception:
   if attempt==4:raise
   time.sleep(min(2**attempt,8))
try:
 current=inventory();pending=[]
 for o in plan['objetos']:
  r=current.get(o['destino'])
  if r:assert r['Size']==o['bytes'] and r['ETag'].strip('"')==o['md5'],'Destino existente diferente'
  else:pending.append(o)
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for start in range(0,len(pending),100):
   done.extend(pool.map(transfer,pending[start:start+100]));(p/'transferencia_parcial.json').write_text(json.dumps(done),encoding='utf-8');print(json.dumps({'transferidos':len(done),'pendientes_iniciales':len(pending)}),flush=True)
 current=inventory()
 for o in plan['objetos']:
  r=current[o['destino']];assert r['Size']==o['bytes'] and r['ETag'].strip('"')==o['md5']
 (p/'transferencia_verificada.json').write_text(json.dumps({'total':len(plan['objetos']),'subidos':len(done),'verificacion':'Tamaño y MD5 remoto, SHA256 local y firmado durante envío','objetos':[{k:o[k] for k in ['clave','destino','bytes','md5','sha256']} for o in plan['objetos']]},ensure_ascii=False,indent=2),encoding='utf-8');print('TRANSFERENCIA_COMPLETA_VERIFICADA',flush=True)
except Exception:
 (p/'transferencia_error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8');print('ERROR_PRIVADO');sys.exit(1)

