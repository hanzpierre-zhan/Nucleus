import sys,json,traceback
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts.copia_datos_local import copiar
p=Path('backups/migracion-anton-final-20261018');p.mkdir(exist_ok=True)
try:
 for name,cred in [('anton','backups/preparacion-anton-20261018/accesos-anton-actual.json'),('nucleus','backups/migracion-modus-20261018/accesos-nucleus.json')]:
  f=p/(name+'_pre_final.db')
  if not f.exists():r=copiar(json.loads(Path(cred).read_text())['DATABASE_URL'],f)
  else:r=json.loads(f.with_suffix('.manifest.json').read_text())
  print(json.dumps({'origen':name,'operativos':r['tablas']['nucleus_data'],'tablas':len(r['tablas'])}),flush=True)
except Exception:
 (p/'error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8');print('ERROR_PRIVADO');sys.exit(1)
