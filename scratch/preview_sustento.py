import os,sys,tempfile,runpy,json
sys.path.insert(0,os.getcwd());tempfile.tempdir=os.path.join(os.getcwd(),'scratch')
c=runpy.run_path('tests/conftest.py');app=c['make_app']()
from db import db
from models import Proyecto,NucleusData,Usuario,ConformidadUsuario
with app.app_context():
    u=Usuario.query.filter_by(username='zeno').one();db.session.add(ConformidadUsuario(usuario_id=u.id,version='2026-10-09'))
    p={p.nombre:p for p in Proyecto.query.all()}
    for i in (1,2):
        d={'_BITACORA_INICIO':'Comentario del WO '+str(i),'INICIO EJECUCION':'2026-10-12 09:00:00','FIN EJECUCION':'2026-10-12 17:00:00'}
        db.session.add(NucleusData(proyecto_id=p['FLM - CLARO'].id,key_value='CM-DEMO-'+str(i),data_json=json.dumps(d)))
    d={'N° COTIZACION':'HW-2026-0000099','ESTADO COTIZACION':'Aprobado','CLIENTE':'CLARO','NUMERO WO':'CM-DEMO-1, CM-DEMO-2','GESTOR':'demo','SUB TOTAL + FEE':'100.00'}
    db.session.add(NucleusData(proyecto_id=p['Cotizaciones'].id,key_value=d['N° COTIZACION'],data_json=json.dumps(d)));db.session.commit()
app.run(host='127.0.0.1',port=5055,use_reloader=False)
