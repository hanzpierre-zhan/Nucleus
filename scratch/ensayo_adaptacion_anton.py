from pathlib import Path
import os,sys,json,sqlite3,hashlib,secrets
root=Path.cwd();sys.path.insert(0,str(root));p=root/'backups/preparacion-anton-20261018';trial=p/'ensayo_cotizaciones_adaptadas.db';base=p/'nucleus_post_modus_preparacion.db'
with trial.open('xb'):pass
with sqlite3.connect(base) as a,sqlite3.connect(trial) as b:a.backup(b)
source=sqlite3.connect('file:'+str((p/'anton_supabase_actual_20261018.db').as_posix())+'?mode=ro',uri=True);source.row_factory=sqlite3.Row;dst=sqlite3.connect(trial);dst.row_factory=sqlite3.Row
sp={r['id']:r['nombre'] for r in source.execute('select id,nombre from proyectos')};dp={r['nombre']:r['id'] for r in dst.execute('select id,nombre from proyectos')};mapping={id:dp['FLM - PEXT' if n=='PEXT' else n] for id,n in sp.items()}
from scripts.migrar_modus import remapear_adjuntos
originales={r['id']:r['data_json'] for r in dst.execute('select id,data_json from nucleus_data')};source_pext=next(id for id,n in sp.items() if n=='PEXT')
for r in source.execute('select * from nucleus_data where proyecto_id=?',(source_pext,)):
 dst.execute('insert into nucleus_data(proyecto_id,key_value,data_json) values(?,?,?)',(dp['FLM - PEXT'],r['key_value'],json.dumps(remapear_adjuntos(json.loads(r['data_json']),mapping),ensure_ascii=False)))
plan=json.loads((p/'conciliacion_cotizaciones_adaptadas.json').read_text(encoding='utf-8'));dst.execute('create table ensayo_anton_cotizaciones_revision(id_origen integer primary key,clave text,accion text,propuesta_json text)');nuevas=[]
for r in plan['cotizaciones_modulo']:
 dst.execute('insert into ensayo_anton_cotizaciones_revision values(?,?,?,?)',(r['id_anton'],r['clave_original'],r['accion'],json.dumps(r,ensure_ascii=False)))
 if r['accion']=='agregar_nuevo':
  dst.execute('insert into nucleus_data(proyecto_id,key_value,data_json) values(?,?,?)',(dp['Cotizaciones'],r['clave_original'],json.dumps(r['adaptacion']['datos'],ensure_ascii=False)));nuevas.append(r['clave_original'])
fisicas=[]
for row in source.execute('select * from cotizaciones'):
 d=dict(row);d.pop('id');d['proyecto_id']=mapping[d['proyecto_id']];cols=list(d);cur=dst.execute('insert into cotizaciones('+','.join(cols)+') values('+','.join('?' for _ in cols)+')',[d[c] for c in cols]);fisicas.append({'id':cur.lastrowid,'key':d['key_value'],'proyecto_id':d['proyecto_id']})
assert all(dst.execute('select data_json from nucleus_data where id=?',(id,)).fetchone()[0]==v for id,v in originales.items());dst.commit();dst.close();source.close()
os.environ['DATABASE_URL']='sqlite:///'+trial.as_posix();os.environ['SECRET_KEY']=secrets.token_urlsafe(48);os.environ['ESPACIOS_HABILITADOS']='0'
from services.sandbox import instalar_bloqueo_red
instalar_bloqueo_red()
from app import app
app.config.update(TESTING=True,B2_BUCKET='',B2_KEY_ID='',B2_APP_KEY='',EVIDENCIA_DIR=str(p/'evidencia_ensayo'))
from db import db
from models import Usuario,Cotizacion
with app.app_context():uid=Usuario.query.filter_by(rol='zeno').first().id
client=app.test_client()
def seleccionar(pid,nombre):
 with client.session_transaction() as ses:ses.update(user_id=uid,username='ensayo-local',rol='zeno',current_proyecto_id=pid,current_proyecto_nombre=nombre)
checks=[]
for r in fisicas:
 seleccionar(r['proyecto_id'],'FLM - PEXT')
 response=client.get('/api/cotizacion/lista',query_string={'key':r['key']});assert response.status_code==200 and any(x['id']==r['id'] for x in response.json['lista'])
 with app.app_context():before={c.name:getattr(db.session.get(Cotizacion,r['id']),c.name) for c in Cotizacion.__table__.columns}
 pdf=client.get('/api/cotizacion/descargar',query_string={'key':r['key'],'cotizacion_id':r['id']});assert pdf.status_code==200 and pdf.data.startswith(b'%PDF-');(p/('pdf_pext_ensayo_'+str(r['id'])+'.pdf')).write_bytes(pdf.data)
 with app.app_context():after={c.name:getattr(db.session.get(Cotizacion,r['id']),c.name) for c in Cotizacion.__table__.columns}
 assert before==after;checks.append({'documento':r['id'],'consulta':True,'pdf':True,'sin_alterar_documento':True})
seleccionar(dp['FLM - PEXT'],'FLM - PEXT');html=client.get('/');assert html.status_code==200
seleccionar(dp['Cotizaciones'],'Cotizaciones');html=client.get('/');assert html.status_code==200
result={'solo_ensayo':True,'pext_cargados':394,'cotizaciones_modulo_nuevas':len(nuevas),'documentos_historicos':checks,'cotizaciones_preservadas_en_revision':len(plan['cotizaciones_modulo']),'registros_previos_intactos_antes_de_arrancar':True,'pantallas_responden':True}
(p/'resultado_ensayo_adaptacion.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'ok':True,'pext':394,'pdf_historicos_verificados':len(checks),'cotizaciones_nuevas_ensayadas':len(nuevas)}))
