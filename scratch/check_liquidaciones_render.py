import os,re,runpy,tempfile,subprocess
from pathlib import Path
tempfile.tempdir=str(Path('scratch').resolve()); c=runpy.run_path('tests/conftest.py');app=c['make_app']();client=app.test_client();client.post('/login',data={'username':'zeno','password':'zeno123','legal_accept':'1'});client.post('/login',data={'consent_step':'1','legal_accept':'1'})
from models import Proyecto
with app.app_context(): proyectos=[(p.id,p.nombre) for p in Proyecto.query.all() if p.nombre in ('Cotizaciones','Rendicion','FLM - CLARO','FLM - INTEGRATEL','FLM - ENTEL')]
node=r'C:\Users\Hanz\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe';total=0
for id,nombre in proyectos:
 client.get('/switch_project/%s'%id)
 response=client.get('/');assert response.status_code==200
 for attrs,code in re.findall(r'<script\b([^>]*)>(.*?)</script>',response.text,re.S):
  if not code.strip() or 'application/json' in attrs:continue
  p=Path('scratch/rendered-check.js');p.write_text(code,encoding='utf-8');r=subprocess.run([node,'--check',str(p)],capture_output=True,text=True);assert r.returncode==0,(nombre,r.stderr);total+=1
assert client.get('/liquidaciones/').status_code==200
print('JavaScript renderizado correcto:',len(proyectos),'módulos,',total,'bloques')
