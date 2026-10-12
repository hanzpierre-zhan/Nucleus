from pathlib import Path
import shutil,sqlite3,json,re,unicodedata,sys
src=Path('C:/Mega/Proyect/Nucleus');dst=Path('C:/Mega/Proyect/Modus')
if dst.exists() and '--reanudar' not in sys.argv:raise SystemExit('El destino ya existe; no se sobrescribe.')
dst.mkdir(exist_ok=True)
for name in ['blueprints','services','migrations','templates','static','tests']:
    if not (dst/name).exists():shutil.copytree(src/name,dst/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','evidencia'))
for name in ['app.py','config.py','db.py','models.py','requirements.txt','Procfile','runtime.txt','.python-version','.gitignore','.gitattributes']:
    shutil.copy2(src/name,dst/name)
(dst/'docs').mkdir(exist_ok=True);(dst/'tools').mkdir(exist_ok=True);(dst/'instance').mkdir(exist_ok=True)
source=sqlite3.connect('file:'+str(src/'nucleus.db').replace('\\','/')+'?mode=ro',uri=True)
out=sqlite3.connect(dst/'modus.db');source.backup(out);source.close()
def norm(v):return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().lower())
def datos(v):
    try:return json.loads(v or '{}')
    except ValueError:return {}
allowed={'FLM - INTEGRATEL','Dataper','Material','Site Name','Generadores','Combustible','Cotizaciones','SITE','Rendicion','Liquidaciones'}
projects=dict(out.execute('select id,nombre from proyectos'))
rows=list(out.execute('select id,proyecto_id,key_value,data_json from nucleus_data'))
flm=[r for r in rows if projects[r[1]]=='FLM - INTEGRATEL']
keys={norm(r[2]) for r in flm};sites=set()
for r in flm:
    for k,v in datos(r[3]).items():
        if norm(k) in ('site','nombresite','nombredesite','sitename','codigosite'):sites.add(norm(v))
keep=set();pending={};counts={}
for rid,pid,key,raw in rows:
    name=projects[pid];d=datos(raw)
    tags=[v for k,v in d.items() if norm(k) in ('proyecto','nombredelproyecto','nombreproyecto','cliente','operador')]
    tagged=any(norm(v) in ('integratel','flmintegratel') for v in tags)
    refs=[v for k,v in d.items() if norm(k) in ('numerowo','numerocmpmplm','wo','numeroocm','cm','site','nombresite','nombredesite','sitename','codigosite')]
    linked=any(norm(v) in keys|sites for v in refs if str(v).strip())
    selected=name=='FLM - INTEGRATEL' or (name in allowed and (tagged or (not tags and linked)))
    if selected:keep.add(rid);counts[name]=counts.get(name,0)+1
    elif name in allowed and not tags:pending[name]=pending.get(name,0)+1
out.execute('delete from token_store')
for table, in out.execute("select name from sqlite_master where type='table'").fetchall():
    cols={r[1] for r in out.execute('pragma table_info("'+table+'")')}
    if table=='nucleus_data':continue
    if 'proyecto_id' in cols:
        pids=[pid for pid,name in projects.items() if name in allowed]
        out.execute('delete from "'+table+'" where proyecto_id not in ('+','.join('?' for _ in pids)+')',pids)
        if table in ('nucleus_history','historial_cambios','cotizaciones','notificaciones') and 'key_value' in cols:
            for pid in pids:
                keptkeys=[r[2] for r in rows if r[0] in keep and r[1]==pid]
                out.execute('delete from "'+table+'" where proyecto_id=? and key_value not in ('+','.join('?' for _ in keptkeys)+')',[pid]+keptkeys)
        if table=='tecnicos':out.execute('delete from tecnicos') # Se reconstruyen desde Personal asignado.
out.execute('delete from refacturable_detalle where origen_id not in ('+','.join('?' for _ in keep)+')',list(keep))
out.execute('delete from nucleus_data where id not in ('+','.join('?' for _ in keep)+')',list(keep))
out.execute('delete from proyectos where nombre not in ('+','.join('?' for _ in allowed)+')',list(allowed))
# Conserva solo administradores y usuarios con acceso a Integratel o autoría en sus registros.
flmids=[pid for pid,name in projects.items() if name=='FLM - INTEGRATEL']
uids={r[0] for r in out.execute('select usuario_id from accesos_proyecto where proyecto_id in ('+','.join('?' for _ in flmids)+')',flmids)}
uids.update(r[0] for r in out.execute("select id from usuarios where rol in ('zeno','suport')"))
autores={str(v).strip().casefold() for r in rows if r[0] in keep for k,v in datos(r[3]).items() if norm(k) in ('gestor','solicitadopor','editadopor')}
uids.update(r[0] for r in out.execute('select id,username from usuarios') if r[1].casefold() in autores)
for table,field in [('accesos_proyecto','usuario_id'),('conformidad_usuario','usuario_id'),('usuarios','id')]:
    out.execute('delete from '+table+' where '+field+' not in ('+','.join('?' for _ in uids)+')',list(uids))
out.commit();out.execute('VACUUM');out.close()
# Copia únicamente los directorios y documentos referidos por los registros conservados.
files=0;missing=0
for r in rows:
    if r[0] not in keep:continue
    for root in ['instance/evidencia','static/evidencia']:
        folder=src/root/str(r[1])/re.sub(r'[^\w.-]','_',r[2])
        if folder.is_dir():shutil.copytree(folder,dst/root/str(r[1])/folder.name,dirs_exist_ok=True);files+=sum(f.is_file() for f in folder.rglob('*'))
    for match in re.findall(r'/api/(?:cotizacion/correo|evidencia/foto)/(\d+)/([^/"\s]+)/([^?"\s]+)',r[3]):
        pid,key,filename=match
        for root in ['instance/evidencia','static/evidencia']:
            f=src/root/pid/key/filename
            if f.is_file():
                target=dst/root/pid/key/filename;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target);files+=1;break
        else:missing+=1
report={'fuente':'C:/Mega/Proyect/Nucleus/nucleus.db','operador':'INTEGRATEL','registros_conservados':counts,'sin_asignacion_excluidos':pending,'archivos_copiados':files,'referencias_sin_archivo_local':missing,'usuarios_conservados':len(uids),'tokens_cloud_copiados':False}
(dst/'docs/separacion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False));print('Proyecto creado:',dst)
