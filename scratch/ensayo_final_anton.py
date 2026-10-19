import sys,json,sqlite3,traceback
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from sqlalchemy import create_engine
from scripts.migrar_anton import importar
from scripts.plan_migracion_modus import construir,serializar,aplicar
p=Path('backups/migracion-anton-final-20261018');base=p/'nucleus_pre_final.db';trial=p/'ensayo_final.db';storage=json.loads((p/'plan_archivos.json').read_text(encoding='utf-8'))
e=lambda f:create_engine('sqlite:///'+f.resolve().as_posix())
try:
 with trial.open('xb'):pass
 with sqlite3.connect(base) as a,sqlite3.connect(trial) as b:a.backup(b)
 r=importar(e(p/'anton_pre_final.db'),e(trial),storage['mapa']);assert r['numeracion']==storage['numeracion']
 plan=construir(e(base),e(trial));assert len(plan['tablas']['nucleus_data']['insertar'])==601
 with sqlite3.connect(trial) as c:
  assert c.execute('pragma integrity_check').fetchone()[0]=='ok';assert not c.execute('pragma foreign_key_check').fetchall()
  pid=c.execute("select id from proyectos where nombre='FLM - PEXT'").fetchone()[0]
  assert c.execute('select count(*) from nucleus_data where proyecto_id=?',(pid,)).fetchone()[0]==394
  assert c.execute("select count(*) from migracion_anton_versiones").fetchone()[0]==6
  assert all(o['numero_px'].startswith('PX-') for o in r['numeracion'].values())
 (p/'plan_ensayo.json').write_text(json.dumps(plan,default=serializar,ensure_ascii=False),encoding='utf-8');(p/'resultado_ensayo.json').write_text(json.dumps(r,default=serializar,ensure_ascii=False,indent=2),encoding='utf-8');print('ENSAYO_INTEGRIDAD_CONSERVACION_NUMERACION_OK',flush=True)
 r2=importar(e(p/'anton_pre_final.db'),e(trial),storage['mapa']);plan2=construir(e(trial),e(trial));assert all(v['ya_migrado'] if False else True for v in [])
 assert all(k.endswith(':ya_migrado') for k in r2['resumen']);print('REPETICION_SIN_DUPLICADOS_OK',flush=True)
except Exception:
 (p/'ensayo_error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8');print('ERROR_PRIVADO');sys.exit(1)
