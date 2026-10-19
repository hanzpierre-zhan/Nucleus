import json,os,subprocess,concurrent.futures,hashlib
from pathlib import Path
from sqlalchemy.engine import make_url
p=Path('backups/migracion-modus-20261018');bin=Path('scratch/postgres-tools/pgsql/bin').resolve()
def backup(name):
 cfg=json.loads((p/f'accesos-{name}.json').read_text());u=make_url(cfg['MODUS_DATABASE_URL' if name=='modus' else 'DATABASE_URL']);env=os.environ.copy();env.update(PGHOST=u.host,PGPORT=str(u.port or 5432),PGDATABASE=u.database,PGUSER=u.username,PGPASSWORD=u.password,PGSSLMODE='require',PGCONNECT_TIMEOUT='15')
 dest=p/f'{name}_nativo_20261018.dump'
 if dest.exists():raise ValueError('Destino existente')
 r=subprocess.run([str(bin/'pg_dump.exe'),'-Fc','--no-password','--file',str(dest.resolve())],env=env,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
 if r.returncode:
  (p/f'{name}_pg_dump_error_privado.txt').write_bytes(r.stderr);raise RuntimeError('pg_dump fallo; diagnostico privado')
 listing=subprocess.run([str(bin/'pg_restore.exe'),'--list',str(dest.resolve())],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
 if listing.returncode:raise RuntimeError('Archivo no verificable')
 (p/f'{name}_nativo_20261018.indice.txt').write_bytes(listing.stdout)
 return {'sistema':name,'bytes':dest.stat().st_size,'sha256':hashlib.file_digest(dest.open('rb'),'sha256').hexdigest(),'indice_verificado':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(backup,['modus','nucleus']))
(p/'respaldos_nativos.manifest.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
