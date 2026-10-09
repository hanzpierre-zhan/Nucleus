import os,sys,tempfile,runpy,json
sys.path.insert(0,os.getcwd());tempfile.tempdir=os.path.join(os.getcwd(),'scratch')
os.environ['PYTHONPATH']=os.environ.get('PYTHONPATH','')
c=runpy.run_path('tests/conftest.py');app=c['make_app']()
from db import db
from models import Proyecto,NucleusData,Usuario,ConformidadUsuario
with app.app_context():
    user=Usuario.query.filter_by(username='zeno').one()
    db.session.add(ConformidadUsuario(usuario_id=user.id,version='2026-10-09'));db.session.commit()
    cot=Proyecto.query.filter_by(nombre='Cotizaciones').one()
    d={'N° COTIZACION':'HW-2026-0000099','ESTADO COTIZACION':'Atendido','SOLICITADO POR':'gestor.demo','CLIENTE':'CLARO','FECHA INICIO OBRA':'2026-10-01','FECHA FIN OBRA':'2026-10-09','SUB TOTAL + FEE':'1250.00','SUBTOTAL FACTURA PROVEEDOR':'900.00','GENERADA':'1','_EVIDENCIA_INICIO':json.dumps(['/static/img/logo.png']),'_BITACORA_INICIO':'Preparación de la obra','ADJUNTO CORREO CLIENTE':'/api/cotizacion/correo/1/demo/correo.msg'}
    db.session.add(NucleusData(proyecto_id=cot.id,key_value=d['N° COTIZACION'],data_json=json.dumps(d)));db.session.commit()
app.run(host='127.0.0.1',port=5055,use_reloader=False)
