import sys, tempfile, os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'preview.db').replace('\\','/')
os.environ['FLASK_ENV']='testing'
from app import app
from flask import session
@app.before_request
def preview_session():
    session['user_id']=1
    session['rol']='zeno'
    session['username']='Preview'
if '--sample' in sys.argv:
    from services import resources
    resources._render=lambda: {'status':'ok','service':'nucleus-peio','plan':'starter','region':'oregon','cpu':{'pct_used':74,'limit_cores':0.1,'sample_seconds':60,'note':'Datos de prueba para diseño.'},'disk':{'free_bytes':4*1024**3,'size_bytes':2*1024**3,'total_bytes':6*1024**3},'memory':{'size_bytes':440*1024**2,'limit_bytes':512*1024**2,'pct_used':85.9,'scope':'Contenedor (cgroup)'},'note':'Datos de prueba para verificar alertas y diseño.'}
    resources._neon=lambda: {'status':'ok','size_bytes':475*1024**2,'limit_bytes':512*1024**2,'pct_used':92.8,'latency_ms':1250,'connections':12,'tables':[{'name':'public.nucleus_data','size_bytes':300*1024**2,'estimated_rows':35000}], 'note':'Datos de prueba; base conectada, incluye índices.'}
    resources._b2=lambda: {'status':'ok','size_bytes':3*1024**3,'limit_bytes':10*1024**3,'pct_used':30,'bucket':'nucleus-demo','files':12500,'versions':13200,'complete':True,'groups':[{'name':'evidencia','size_bytes':2*1024**3,'files':9000}], 'note':'Datos de prueba; incluye versiones anteriores.'}
app.run(port=5100,debug=False)
