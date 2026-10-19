import sys,json
from pathlib import Path
from sqlalchemy import create_engine
sys.path.insert(0,str(Path.cwd()))
from scripts.copia_datos_local import copiar
from scripts.plan_migracion_modus import construir
p=Path('backups/migracion-anton-final-20261018');f=p/'anton_confirmacion_corte.db';c=json.loads(Path('backups/preparacion-anton-20261018/accesos-anton-actual.json').read_text());copiar(c['DATABASE_URL'],f)
e=lambda f:create_engine('sqlite:///'+f.resolve().as_posix());plan=construir(e(p/'anton_pre_final.db'),e(f));assert all(not s['insertar'] and not s['actualizar'] for s in plan['tablas'].values());(p/'origen_confirmado_sin_cambios.json').write_text(json.dumps({'sin_cambios':True,'tablas':len(plan['tablas'])}),encoding='utf-8');print('ORIGEN_ACTUAL_SIN_CAMBIOS_CONFIRMADO')
