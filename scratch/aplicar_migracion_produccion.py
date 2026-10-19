import json,sys,traceback
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path.cwd()));from scripts.plan_migracion_modus import aplicar
p=Path('backups/migracion-modus-20261018');plan=json.loads((p/'plan_produccion_privado.json').read_text(encoding='utf-8'));c=json.loads((p/'accesos-nucleus.json').read_text());transfer=json.loads((p/'transferencia_b2_verificada.json').read_text(encoding='utf-8'));assert transfer['total']==34
u=make_url(c['DATABASE_URL']).set(drivername='postgresql+psycopg2').update_query_dict({'connect_timeout':'15'});e=create_engine(u,hide_parameters=True)
try:
 resultado=aplicar(plan,e)
 (p/'carga_produccion_verificada.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':True,'resultado':resultado}))
except Exception as ex:
 (p/'carga_error_privado.txt').write_text(traceback.format_exc(),encoding='utf-8');print(json.dumps({'ok':False,'tipo_error':type(ex).__name__,'motivo':str(ex) if isinstance(ex,ValueError) else 'Detalles guardados en diagnostico privado'}));sys.exit(1)
finally:e.dispose()
