import os,sys,tempfile,runpy,json
sys.path.insert(0,os.getcwd());tempfile.tempdir=os.path.join(os.getcwd(),'scratch')
c=runpy.run_path('tests/conftest.py');app=c['make_app']()
from db import db
from models import Proyecto,NucleusData,Usuario,ConformidadUsuario
with app.app_context():
    u=Usuario.query.filter_by(username='zeno').one();db.session.add(ConformidadUsuario(usuario_id=u.id,version='2026-10-09'))
    p={p.nombre:p for p in Proyecto.query.all()}
    for nombre,persona in [('FLM - ENTEL','Carlos · Entel'),('FLM - CLARO','Ana · Claro'),('FLM - INTEGRATEL','Luis · Integratel')]:
        db.session.add(NucleusData(proyecto_id=p['Dataper'].id,key_value=persona,data_json=json.dumps({'TECNICO':persona,'PROYECTO':nombre,'ESTADO':'ACTIVO','CONTRATA':'COBRA'})))
        db.session.add(NucleusData(proyecto_id=p['Material'].id,key_value=nombre,data_json=json.dumps({'PROYECTO':nombre,'DESCRIPCION_MATERIAL':'Material para '+nombre,'COD_MATERIAL':nombre,'UM':'UND'})))
    db.session.add(NucleusData(proyecto_id=p['SITE'].id,key_value='SITE-QA',data_json=json.dumps({'NOMBRE DE SITE':'SITE AREQUIPA DEMO','Departamento':'Arequipa'})))
    db.session.add(NucleusData(proyecto_id=p['FLM - CLARO'].id,key_value='WO-QA',data_json=json.dumps({'NOMBRE DE SITE':'SITE AREQUIPA DEMO','DEPARTAMENTO':'Arequipa','CODIGO INTERNO':'CI-CL-2026-0000001'})))
    db.session.commit()
app.run(host='127.0.0.1',port=5055,use_reloader=False)
