import json,sys
from pathlib import Path
import boto3
from botocore.config import Config
p=Path('backups/preparacion-anton-20261018');c=json.loads((p/'accesos-anton-actual.json').read_text());s=boto3.client('s3',endpoint_url=c['B2_ENDPOINT_URL'],aws_access_key_id=c['B2_KEY_ID'],aws_secret_access_key=c['B2_APP_KEY'],region_name=c['B2_REGION'],config=Config(connect_timeout=15,read_timeout=45,retries={'max_attempts':1}));result=[]
for o in json.loads((p/'archivos_referidos_ausentes.json').read_text()):
 try:
  r=s.list_object_versions(Bucket=c['B2_BUCKET'],Prefix=o['clave'],MaxKeys=30);result.append({'clave':o['clave'],'versiones':len([v for v in r.get('Versions',[]) if v['Key']==o['clave']]),'borrados':len(r.get('DeleteMarkers',[]))})
 except Exception as ex:result.append({'clave':o['clave'],'consulta_no_disponible':type(ex).__name__})
Path('backups/migracion-anton-final-20261018/recuperacion_fotos_ausentes.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'revisados':len(result),'versiones_recuperables':sum(r.get('versiones',0) for r in result)}))
