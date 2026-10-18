"""Conciliación offline aditiva de referencias exactas; nunca reemplaza registros."""
import argparse,hashlib,json,re,sqlite3,unicodedata
from collections import defaultdict,Counter
from datetime import datetime
from pathlib import Path

MAPA={'PEXT':'FLM - PEXT','FLM - PEXT':'FLM - PEXT','FLM - ENTEL':'FLM - ENTEL','FLM - CLARO':'FLM - CLARO','FLM - INTEGRATEL':'FLM - INTEGRATEL'}

def normalizar(v):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().casefold())
def negocio(v):return {'entel':'FLM - ENTEL','flmentel':'FLM - ENTEL','claro':'FLM - CLARO','flmclaro':'FLM - CLARO','integratel':'FLM - INTEGRATEL','flmintegratel':'FLM - INTEGRATEL','pext':'FLM - PEXT','entelpext':'FLM - PEXT','flmpext':'FLM - PEXT'}.get(normalizar(v))
def abrir(path):
    c=sqlite3.connect('file:'+Path(path).resolve().as_posix()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c

def planificar(base,fuentes,fuentes_generadores=(),fuentes_entel=()):
    indices=defaultdict(list);metadatos=[]
    for ruta,alcance in [(p,None) for p in fuentes]+[(p,'Generadores') for p in fuentes_generadores]+[(p,'FLM - ENTEL') for p in fuentes_entel]:
        ruta=Path(ruta).resolve();sha=hashlib.sha256(ruta.read_bytes()).hexdigest()
        with abrir(ruta) as src:
            if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Fuente sin integridad: '+ruta.name)
            nombres=dict(src.execute('SELECT id,nombre FROM proyectos'))
            for r in src.execute('SELECT id,proyecto_id,key_value,data_json FROM nucleus_data'):
                nombre=nombres[r['proyecto_id']];dest=MAPA.get(nombre) or ('Generadores' if nombre=='Generadores' else None)
                if not dest or (alcance and dest!=alcance):continue
                d=json.loads(r['data_json'])
                if not isinstance(d,dict):continue
                referencia=str(d.get('QR ASIGNADO') or '').strip().casefold() if dest=='Generadores' else r['key_value'].strip().casefold()
                if referencia:indices[(dest,referencia)].append({'fuente':ruta.name,'sha256':sha,'origen_id':str(r['id']),'modulo':dest,'clave':r['key_value'],'datos':d})
        metadatos.append({'archivo':ruta.name,'sha256':sha})
    propuestos={};pendientes=[];resueltos=Counter()
    with abrir(base) as con:
        nombres=dict(con.execute('SELECT id,nombre FROM proyectos'));destinos={n:pid for pid,n in nombres.items()}
        existentes=set()
        for r in con.execute('SELECT proyecto_id,key_value,data_json FROM nucleus_data'):
            n=nombres[r['proyecto_id']]
            valor=str(json.loads(r['data_json']).get('QR ASIGNADO') or '').strip().casefold() if n=='Generadores' else r['key_value'].strip().casefold()
            if valor:existentes.add((n,valor))
        referencias=[]
        for r in con.execute('SELECT id,proyecto_id,data_json FROM nucleus_data'):
            modulo=nombres[r['proyecto_id']]
            if modulo not in ('Rendicion','Cotizaciones','Combustible'):continue
            d=json.loads(r['data_json']);esperado=negocio(d.get('Nombre del proyecto') or d.get('CLIENTE') or d.get('PROYECTO'))
            for k,v in d.items():
                if normalizar(k) in ('numerocmpmplm','numerowo','numerodewo','wonumber') and isinstance(v,(str,int)):
                    for codigo in re.split(r'[,;\r\n|]+',str(v)):
                        if codigo.strip():referencias.append((r['id'],modulo,codigo.strip(),esperado,'WO'))
            if modulo=='Combustible' and str(d.get('QR ASIGNADO') or '').strip():referencias.append((r['id'],modulo,str(d['QR ASIGNADO']).strip(),None,'QR'))
        for rid,modulo,codigo,esperado,tipo in referencias:
            permitidos=['Generadores'] if tipo=='QR' else [esperado] if esperado else list(set(MAPA.values()))
            llave=codigo.casefold()
            encontrados=[(m,llave) for m in permitidos if (m,llave) in existentes]
            if len(encontrados)==1:resueltos['ya_existente']+=1;continue
            if len(encontrados)>1:pendientes.append({'registro_id':rid,'modulo':modulo,'tipo':tipo,'motivo':'clave_ambigua_en_activa'});continue
            candidatos=[x for m in permitidos for x in indices.get((m,llave),[])]
            grupos=defaultdict(list)
            for candidato in candidatos:
                firma=(candidato['modulo'],candidato['clave'].strip().casefold(),json.dumps(candidato['datos'],sort_keys=True,ensure_ascii=False))
                grupos[firma].append(candidato)
            if len(grupos)!=1:
                pendientes.append({'registro_id':rid,'modulo':modulo,'tipo':tipo,'motivo':'sin_fuente_exacta' if not grupos else 'fuentes_en_conflicto'});continue
            candidato=next(iter(grupos.values()))[0]
            if candidato['modulo'] not in destinos:
                pendientes.append({'registro_id':rid,'modulo':modulo,'tipo':tipo,'motivo':'modulo_destino_ausente'});continue
            clave=(candidato['modulo'],candidato['clave'].strip().casefold())
            if clave not in propuestos:propuestos[clave]={**candidato,'proyecto_id':destinos[candidato['modulo']],'referencias':[]}
            propuestos[clave]['referencias'].append({'registro_id':rid,'modulo':modulo,'tipo':tipo});resueltos['referencias_recuperables']+=1
    return {'fuentes':metadatos,'insertar':list(propuestos.values()),'pendientes':pendientes,'conteos':dict(resueltos)}


def aplicar(base,plan):
    with sqlite3.connect(base) as con:
        con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON');con.execute('BEGIN IMMEDIATE')
        con.execute('''CREATE TABLE IF NOT EXISTS conciliacion_origen(id INTEGER PRIMARY KEY,fuente_sha256 VARCHAR(64) NOT NULL,fuente VARCHAR(160) NOT NULL,origen_id VARCHAR(80) NOT NULL,destino_id INTEGER NOT NULL REFERENCES nucleus_data(id),original_json TEXT NOT NULL,creado_en DATETIME NOT NULL,UNIQUE(fuente_sha256,origen_id))''')
        cambios=[]
        for p in plan['insertar']:
            existe=con.execute('SELECT id FROM nucleus_data WHERE proyecto_id=? AND lower(trim(key_value))=?',(p['proyecto_id'],p['clave'].strip().casefold())).fetchone()
            if existe:continue
            nombre=con.execute('SELECT nombre FROM proyectos WHERE id=?',(p['proyecto_id'],)).fetchone()
            if not nombre or nombre[0]!=p['modulo']:raise ValueError('El proyecto destino cambió; vuelve a planificar.')
            raw=json.dumps(p['datos'],ensure_ascii=False)
            cursor=con.execute('INSERT INTO nucleus_data(proyecto_id,key_value,data_json) VALUES(?,?,?)',(p['proyecto_id'],p['clave'],raw));destino=cursor.lastrowid
            con.execute('INSERT INTO conciliacion_origen(fuente_sha256,fuente,origen_id,destino_id,original_json,creado_en) VALUES(?,?,?,?,?,?)',(p['sha256'],p['fuente'],p['origen_id'],destino,raw,datetime.utcnow().isoformat()))
            cambios.append({'destino_id':destino,'modulo':p['modulo'],'fuente':p['fuente'],'origen_id':p['origen_id']})
        if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('La conciliación dejaría referencias rotas.')
        return cambios


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--db',type=Path,required=True);a.add_argument('--fuente',type=Path,action='append',required=True);a.add_argument('--generadores',type=Path,action='append',default=[]);a.add_argument('--entel',type=Path,action='append',default=[]);a.add_argument('--salida',type=Path,required=True);a.add_argument('--aplicar',action='store_true');args=a.parse_args()
    plan=planificar(args.db,args.fuente,args.generadores,args.entel);args.salida.parent.mkdir(parents=True,exist_ok=True)
    if args.aplicar:
        respaldo=args.salida.with_suffix('.previo.db')
        with respaldo.open('xb'):pass
        with abrir(args.db) as src,sqlite3.connect(respaldo) as dst:src.backup(dst)
        plan['aplicados']=aplicar(args.db,plan)
    args.salida.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'registros_propuestos':len(plan['insertar']),'insertados':len(plan.get('aplicados',[])),'pendientes':len(plan['pendientes']),'conteos':plan['conteos']}))
