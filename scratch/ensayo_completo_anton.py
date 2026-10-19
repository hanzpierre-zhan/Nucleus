import sys,json,sqlite3,traceback
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from sqlalchemy import create_engine
from scripts.migrar_anton import importar
from scripts.plan_migracion_modus import construir,serializar
p=Path('backups/preparacion-anton-20261018'); trial=p/'ensayo_completo_px_v1.db'
try:
 with trial.open('xb'):pass
 with sqlite3.connect(p/'nucleus_post_modus_preparacion.db') as a,sqlite3.connect(trial) as b:a.backup(b)
 e=lambda f:create_engine('sqlite:///'+f.resolve().as_posix())
 r=importar(e(p/'anton_supabase_actual_20261018.db'),e(trial))
 plan=construir(e(p/'nucleus_post_modus_preparacion.db'),e(trial))
 (p/'ensayo_completo_px_v1.json').write_text(json.dumps(r,default=serializar,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(r['resumen']))
 r2=importar(e(p/'anton_supabase_actual_20261018.db'),e(trial))
 assert all(v['cantidad_despues']==construir(e(p/'nucleus_post_modus_preparacion.db'),e(trial))['tablas'][k]['cantidad_despues'] for k,v in plan['tablas'].items())
 print('REPETICION_OK')
except Exception:
 (p/'ensayo_completo_error.txt').write_text(traceback.format_exc(),encoding='utf-8'); print(traceback.format_exc().splitlines()[-1]);sys.exit(1)
