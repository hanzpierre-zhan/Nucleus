import os,sys,json,secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
folder=Path(json.loads((root/'backups/ultimo-ensayo-espacios.json').read_text())['carpeta'])
os.environ['DATABASE_URL']='sqlite:///'+(folder/'trabajo.db').as_posix()
os.environ['ESPACIOS_HABILITADOS']='1'
os.environ['SECRET_KEY']=secrets.token_urlsafe(48)
from services.sandbox import instalar_bloqueo_red,instalar_guardas_http
instalar_bloqueo_red()
from app import app
app.jinja_env.auto_reload=True
app.config['SESSION_COOKIE_NAME']='nucleus_ensayo_5001'
app.config['EVIDENCIA_DIR']=str(folder/'adjuntos-locales')
instalar_guardas_http(app)
app.run(host='127.0.0.1',port=5001,debug=False,use_reloader=False)
