from pathlib import Path
import os,sys,json,sqlite3,secrets
root=Path.cwd();sys.path.insert(0,str(root));p=root/'backups/migracion-anton-final-20261018';trial=p/'ensayo_final.db'
with sqlite3.connect(trial) as c:
 c.row_factory=sqlite3.Row
 dp={r['nombre']:r['id'] for r in c.execute('select id,nombre from proyectos')}
 fisicas=[{'id':r['id'],'key':r['key_value'],'proyecto_id':r['proyecto_id']} for r in c.execute("select c.* from cotizaciones c join migracion_anton_origen m on m.tabla='cotizaciones' and cast(c.id as text)=m.id_destino")]
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

(p/'ensayo_ui_ok.json').write_text(json.dumps({'documentos':checks,'pantallas':True}),encoding='utf-8');print('PDF_HISTORICOS_Y_PANTALLAS_OK')
