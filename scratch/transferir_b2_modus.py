import json,hashlib,mimetypes,concurrent.futures,base64
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from urllib.parse import quote
import urllib.request
from urllib.error import HTTPError
p=Path('backups/migracion-modus-20261018');c=json.loads((p/'accesos-nucleus.json').read_text());m=json.loads((p/'respaldo_b2_modus_20261018.manifest.json').read_text(encoding='utf-8'))
s=boto3.client('s3',endpoint_url=c['B2_ENDPOINT_URL'],aws_access_key_id=c['B2_KEY_ID'],aws_secret_access_key=c['B2_APP_KEY'],region_name=c['B2_REGION'],config=Config(connect_timeout=15,read_timeout=60,retries={'max_attempts':3},request_checksum_calculation='when_required',response_checksum_validation='when_required',s3={'addressing_style':'path','payload_signing_enabled':True}))
def transferir(o):
 f=Path(o['archivo_local']);f=f if f.is_absolute() else p/f
 data=f.read_bytes()
 assert hashlib.sha256(data).hexdigest()==o['sha256'] and len(data)==o['bytes']
 accion='cargado'
 existe=any(r['Key']==o['clave'] for r in s.list_objects_v2(Bucket=c['B2_BUCKET'],Prefix=o['clave'],MaxKeys=2).get('Contents',[]))
 if existe:accion='existente_verificado'
 else:
  url=c['B2_ENDPOINT_URL'].rstrip('/')+'/'+quote(c['B2_BUCKET'],safe='')+'/'+quote(o['clave'],safe='/')
  req=AWSRequest(method='PUT',url=url,data=data,headers={'Content-Type':mimetypes.guess_type(o['clave'])[0] or 'application/octet-stream','x-amz-content-sha256':o['sha256'],'Content-MD5':base64.b64encode(hashlib.md5(data).digest()).decode()})
  SigV4Auth(Credentials(c['B2_KEY_ID'],c['B2_APP_KEY']),'s3',c['B2_REGION']).add_auth(req)
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=dict(req.headers),method='PUT'),timeout=60) as response:response.read()
 listado=s.list_objects_v2(Bucket=c['B2_BUCKET'],Prefix=o['clave'],MaxKeys=2).get('Contents',[])
 actual=next(r for r in listado if r['Key']==o['clave'])
 assert actual['Size']==len(data) and actual['ETag'].strip('"')==hashlib.md5(data).hexdigest()
 return {'clave':o['clave'],'sha256_local':o['sha256'],'md5_remoto':actual['ETag'],'bytes':len(data),'accion':accion,'verificacion':'tamano y MD5 remoto; SHA256 local y firmado al enviar'}

try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(transferir,m['objetos']))
 (p/'transferencia_b2_verificada.json').write_text(json.dumps({'objetos':result,'total':len(result),'bytes':sum(o['bytes'] for o in result)},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':True,'objetos_verificados':len(result)}))
except Exception as e:
 import traceback
 (p/'transferencia_error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8')
 print(json.dumps({'ok':False,'tipo_error':type(e).__name__}));raise SystemExit(1)

