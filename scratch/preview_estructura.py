import os,sys,tempfile,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
reuse=os.environ.get('NUCLEUS_PREVIEW_DB')
if reuse:
    preview=Path(reuse).resolve()
    if not preview.is_relative_to(root/'scratch') or preview.name!='preview.db' or not preview.parent.name.startswith('performance-'):
        raise ValueError('La vista previa solo puede reutilizar una copia temporal de pruebas.')
    folder=preview.parent
else:
    folder=Path(tempfile.mkdtemp(prefix='performance-',dir=root/'scratch'))
    src=sqlite3.connect('file:'+str(root/'nucleus.db').replace('\\','/')+'?mode=ro',uri=True)
    dst=sqlite3.connect(folder/'preview.db');src.backup(dst);dst.close();src.close()
os.environ['DATABASE_URL']='sqlite:///'+str(folder/'preview.db').replace('\\','/')
os.environ['SECRET_KEY']='preview-local-secret'
from app import app
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['EVIDENCIA_DIR']=str(folder/'evidencia')
app.config['B2_BUCKET']=''
from db import db
from models import Usuario,ConformidadUsuario
from werkzeug.security import generate_password_hash
with app.app_context():
    if not Usuario.query.filter_by(username='performance-preview').first():
        u=Usuario(username='performance-preview',password_hash=generate_password_hash('preview-local'),rol='zeno')
        db.session.add(u);db.session.flush();db.session.add(ConformidadUsuario(usuario_id=u.id,version='2026-10-09'));db.session.commit()
app.run(host='127.0.0.1',port=5065,debug=False)

