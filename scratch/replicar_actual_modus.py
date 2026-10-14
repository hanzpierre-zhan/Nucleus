from pathlib import Path
from datetime import datetime
import shutil,zipfile,sqlite3,json,hashlib,re
src=Path('C:/Mega/Proyect/Nucleus').resolve();dst=Path('C:/Mega/Proyect/Modus').resolve()
assert src!=dst and dst.name=='Modus' and dst.is_dir()
preserve={'blueprints/auth.py','blueprints/imports.py','blueprints/wo.py','services/utilidades.py','migrations/__init__.py','tests/conftest.py'}
files=[]
for folder in ['blueprints','services','migrations','templates','static','tests']:
 for p in (src/folder).rglob('*'):
  if p.is_file() and not any(part in ('__pycache__','evidencia') for part in p.parts) and p.suffix!='.pyc' and p.relative_to(src).as_posix() not in preserve:files.append(p.relative_to(src))
files += [Path(x) for x in ['app.py','db.py','models.py','requirements.txt','Procfile','runtime.txt','.python-version','iniciar.cmd'] if (src/x).exists()]
# Back up code and the destination database independently. No database replication.
backup=dst/'backups'/('replica-nucleus-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True)
with zipfile.ZipFile(backup/'codigo-anterior.zip','w',zipfile.ZIP_DEFLATED) as z:
 for rel in files:
  if (dst/rel).is_file():z.write(dst/rel,rel.as_posix())
 cpath=dst/'config.py';z.write(cpath,'config.py')
source=sqlite3.connect('file:'+str(dst/'modus.db').replace('\\','/')+'?mode=ro',uri=True)
output=sqlite3.connect(backup/'modus.db');source.backup(output);output.close()
counts=dict(source.execute('select p.nombre,count(*) from nucleus_data n join proyectos p on p.id=n.proyecto_id group by p.nombre'))
source.close()
old={rel:(dst/rel).read_text(encoding='utf-8') for rel in ['templates/base.html','templates/login.html','templates/index.html','blueprints/admin.py']}
for rel in files:
 p=src/rel;q=dst/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
def edit(rel,fn):
 p=dst/rel;p.write_text(fn(p.read_text(encoding='utf-8')),encoding='utf-8')
def brand(s):return s.replace('Nucleus','Modus').replace('NUCLEUS','MODUS').replace('nucleus-theme','modus-theme').replace('nucleus-sidebar','modus-sidebar').replace('X-Modus-Project','X-Nucleus-Project')
for rel in files:
 if rel.parts[0]=='templates':edit(rel,brand)
# Keep the logo upload feature and the original Modus monogram.
def base(s):
 s=re.sub(r'<link rel="icon"[^>]+>', '<link rel="icon" type="image/svg+xml" href="/static/img/modus.svg">',s,count=1)
 oldsvg=re.search(r'<svg.*?</svg>',old['templates/base.html'],re.S).group()
 s=re.sub(r'<svg.*?</svg>',lambda m:oldsvg,s,count=1,flags=re.S)
 start=old['templates/base.html'].index("                    {% if session.get('rol') in ['zeno', 'suport'] %}",old['templates/base.html'].index('sidebar-user'))
 end=old['templates/base.html'].index('                    {% endif %}',start)+len('                    {% endif %}')
 logo=old['templates/base.html'][start:end]
 s=re.sub(r'                    <div class="user-avatar".*?</div>',lambda m:logo,s,count=1)
 scripts='    <script src="{{ url_for(\'static\', filename=\'js/column-filters.js\') }}?v=1"></script>\n    {% if session.get(\'rol\') in [\'zeno\', \'suport\'] %}<script src="{{ url_for(\'static\', filename=\'js/branding.js\') }}?v=1"></script>{% endif %}\n'
 return s.replace('</body>',scripts+'</body>')
edit('templates/base.html',base)
def login(s):
 logo=re.search(r'<a href="/" class="vl-logo".*?</a>',old['templates/login.html'],re.S).group()
 s=re.sub(r'<a href="/" class="vl-logo".*?</a>',lambda m:logo,s,count=1,flags=re.S)
 return re.sub(r'<link rel="icon"[^>]+>','<link rel="icon" type="image/svg+xml" href="/static/img/modus.svg">',s,count=1)
edit('templates/login.html',login)
def admin(s):
 start=old['blueprints/admin.py'].index("@bp.route('/api/branding/logo'")
 end=old['blueprints/admin.py'].index("@bp.route('/api/debug/dataper'",start)
 return s.replace("@bp.route('/api/debug/dataper'",old['blueprints/admin.py'][start:end]+"@bp.route('/api/debug/dataper'",1)
edit('blueprints/admin.py',admin)
def app(s):
 s=s.replace('current_app\n','current_app, session\n',1)
 s=s.replace("database_url = os.environ.get('DATABASE_URL', '')","database_url = os.environ.get('MODUS_DATABASE_URL', '')")
 s=s.replace('    # Migraciones de base de datos (idempotentes)','    from services.operador import instalar, preparar_configuracion\n    instalar(app)\n\n    # Migraciones de base de datos (idempotentes)',1)
 s=s.replace('        numerar_historicos()','        numerar_historicos()\n        if app.config.get("MODUS_SCOPE"):\n            preparar_configuracion()',1)
 s=s.replace("return {'flm_resource_context': contexto_recursos()}","from services.branding import logo_url\n        return {'flm_resource_context': contexto_recursos(), 'sidebar_logo_url': logo_url() if session.get('user_id') else None}")
 s=s.replace("'.venv' / 'Scripts'","'.venv-local' / 'Scripts'").replace('con .venv…','con .venv-local…')
 return brand(s).replace('app.run(debug=True, port=int(os.environ.get(\'PORT\', 5001)))','app.run(debug=app.config[\'DEBUG\'], port=int(os.environ.get(\'PORT\', 5002)))')
edit('app.py',app)
edit('blueprints/pages.py',lambda s:s.replace("('FLM', 'FLM - ENTEL', 'PEXT')","('FLM', 'FLM - ENTEL', 'PEXT', 'FLM - INTEGRATEL')").replace("('FLM', 'FLM - ENTEL')","('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL')"))
edit('services/apoyo.py',lambda s:s.replace('/Nucleus/','/Modus/'))
edit('services/resources.py',lambda s:s.replace('Configura B2_BUCKET, B2_KEY_ID y B2_APP_KEY.','Configura MODUS_B2_BUCKET, MODUS_B2_KEY_ID y MODUS_B2_APP_KEY.'))
def index(s):
 s=s.replace("{{ pk }}\";","{{ 'Ticket ID (WO)' if pk == 'Ticket ID' and session.get('current_proyecto_nombre') == 'FLM - INTEGRATEL' else pk }}\";",1)
 for begin in ['clearBtn.onclick = (ex) => {','clearBtn.onclick = function (ex) {']:
  a=old['templates/index.html'].index(begin);b=old['templates/index.html'].index('          };',a)+len('          };')
  c=s.index(begin);e=s.index('          };',c)+len('          };')
  s=s[:c]+old['templates/index.html'][a:b]+s[e:]
 a=old['templates/index.html'].index('        // Auxiliares vacíos de Integratel:')
 b=old['templates/index.html'].index('\n        if ',old['templates/index.html'].index('            colDef.visible = false;',a)+1)
 extra=old['templates/index.html'][a:b]
 # Preserve empty auxiliary-column defaults before manual-column visibility logic.
 pos=s.index('        // Manual columns ocultas por defecto')
 return s[:pos]+extra+'\n'+s[pos:]
edit('templates/index.html',index)
edit('iniciar.cmd',lambda s:s.replace('.venv','.venv-local').replace('Nucleus','Modus'))
with (dst/'.gitignore').open('a',encoding='utf-8') as f:f.write('\n.venv-local/\nbackups/\n')
report={'fecha':datetime.now().isoformat(),'origen':str(src),'destino':str(dst),'archivos_actualizados':len(files),'respaldo':str(backup),'registros_antes':counts,'archivos_especificos_preservados':sorted(preserve)}
(dst/'docs/replica-nucleus-actual.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'archivos':len(files),'respaldo':str(backup),'registros':counts},ensure_ascii=True))
