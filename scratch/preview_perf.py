import os,sys,tempfile,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
folder=Path(tempfile.mkdtemp(prefix='performance-',dir=root/'scratch'))
src=sqlite3.connect('file:'+str(root/'nucleus.db').replace('\\','/')+'?mode=ro',uri=True)
dst=sqlite3.connect(folder/'preview.db');src.backup(dst);dst.close();src.close()
os.environ['DATABASE_URL']='sqlite:///'+str(folder/'preview.db').replace('\\','/')
from app import app
from db import db
from models import Usuario,ConformidadUsuario
from werkzeug.security import generate_password_hash
with app.app_context():
    u=Usuario(username='performance-preview',password_hash=generate_password_hash('preview-local'),rol='zeno')
    db.session.add(u);db.session.flush();db.session.add(ConformidadUsuario(usuario_id=u.id,version='2026-10-09'));db.session.commit()
app.run(host='127.0.0.1',port=5056,debug=False)
