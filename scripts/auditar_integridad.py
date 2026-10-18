"""Auditoría local de solo lectura; los informes no contienen datos personales."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib,json,re,sqlite3,unicodedata
from pathlib import Path


def norm(v):
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower())


def q(v):return '"'+v.replace('"','""')+'"'


def audit(database,root):
    database,root=Path(database).resolve(),Path(root).resolve()
    source={}
    for carpeta in ('blueprints','services','templates','static/js','tests'):
        for p in (root/carpeta).rglob('*'):
            if p.suffix in ('.py','.js','.html','.json') and not any(x in p.parts for x in ('__pycache__','vendor')) and '.min.' not in p.name:
                source[str(p.relative_to(root)).replace('\\','/')]=norm(p.read_text(encoding='utf-8',errors='replace'))
    out={'alcance':'Copia local; no certifica integraciones externas ni datos no exportados',
         'tablas':{},'errores_json':[],'proyectos':{},'columnas':[],'limpieza_segura':[], 'correlaciones':{}}
    with sqlite3.connect('file:'+database.as_posix()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        out['integridad']=[r[0] for r in c.execute('PRAGMA integrity_check')]
        out['referencias_rotas']=[{'tabla':r[0],'fila_interna':r[1],'destino':r[2]} for r in c.execute('PRAGMA foreign_key_check')]
        tablas=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tablas:
            info=c.execute('PRAGMA table_info('+q(t)+')').fetchall()
            out['tablas'][t]={'filas':c.execute('SELECT COUNT(*) FROM '+q(t)).fetchone()[0],
                'columnas':[{'nombre':r['name'],'tipo':r['type'],'obligatoria':bool(r['notnull']),'pk':bool(r['pk'])} for r in info],
                'relaciones':[{'columna':r['from'],'destino':r['table'],'campo':r['to']} for r in c.execute('PRAGMA foreign_key_list('+q(t)+')')]}
        # Inspeccionar columnas JSON de todas las tablas, no solo registros operativos.
        for t,info in out['tablas'].items():
            if t in ('nucleus_data','nucleus_history'):continue
            campos=[x['nombre'] for x in info['columnas'] if x['nombre'].endswith('_json') or x['nombre']=='restricciones']
            for campo in campos:
                for num,r in enumerate(c.execute('SELECT '+q(campo)+' FROM '+q(t)),1):
                    if r[0] in (None,''):continue
                    try:json.loads(r[0])
                    except (ValueError,TypeError):out['errores_json'].append({'tabla':t,'columna':campo,'posicion':num})
        nombres=dict(c.execute('SELECT id,nombre FROM proyectos'))
        rows=defaultdict(list);keys=defaultdict(Counter);filled=defaultdict(Counter);historic=defaultdict(Counter)
        for t in ('nucleus_data','nucleus_history'):
            for r in c.execute('SELECT id,proyecto_id,key_value,data_json FROM '+t):
                try:d=json.loads(r['data_json']);assert isinstance(d,dict)
                except (ValueError,TypeError,AssertionError):
                    out['errores_json'].append({'tabla':t,'id':r['id']});continue
                if t=='nucleus_data':
                    rows[r['proyecto_id']].append((r['id'],r['key_value'],d));keys[r['proyecto_id']].update(d.keys())
                    filled[r['proyecto_id']].update(k for k,v in d.items() if v not in ('',None,[],{}))
                else:historic[r['proyecto_id']].update(d.keys())
        configs=defaultdict(dict)
        for r in c.execute('SELECT id,proyecto_id,clave,valor FROM app_config'):
            estructura = r['clave'] in ('app_schema','manual_columns','column_layout') or r['clave'].startswith('column_layout__')
            try:
                v=json.loads(r['valor'])
                if estructura and not isinstance(v,list):
                    out['errores_json'].append({'tabla':'app_config','id':r['id'],'estructura':'Se esperaba una lista'})
            except (ValueError,TypeError):
                v=r['valor']
                if estructura:out['errores_json'].append({'tabla':'app_config','id':r['id']})
            configs[r['proyecto_id']][r['clave']]=(r['id'],v)
        for pid,nombre in nombres.items():
            cfg=configs[pid];schema=cfg.get('app_schema',(None,[]))[1]
            manual=cfg.get('manual_columns',(None,[]))[1]
            schema=schema if isinstance(schema,list) else []
            manual=manual if isinstance(manual,list) else []
            declaradas={x['nombre'] for x in manual if isinstance(x,dict) and isinstance(x.get('nombre'),str)}
            fields=set(keys[pid])|declaradas|{x for x in schema if isinstance(x,str)}
            contextos=norm(json.dumps({k:v for k,(_,v) in cfg.items() if k!='app_schema' and not k.startswith('column_layout')},ensure_ascii=False))
            out['proyectos'][nombre]={'filas':len(rows[pid]),'campos_totales':len(fields),'campos_sin_valores':sum(not filled[pid][f] for f in fields)}
            for f in sorted(fields):
                n=norm(f);refs=[p for p,txt in source.items() if len(n)>2 and n in txt]
                derivada=bool(refs) or f.startswith('_')
                artifact=bool(re.fullmatch(r'(?:unnamed[: _]*\d*|column\d+|columna\d+|)',f,re.I))
                seguro=(artifact and not refs and f not in declaradas and n not in contextos and not filled[pid][f] and not historic[pid][f])
                estado='con_datos' if filled[pid][f] else 'declarada_formulario' if f in declaradas else 'referenciada_codigo' if derivada else 'requiere_revision'
                out['columnas'].append({'proyecto':nombre,'campo':f,'presente_en_filas':keys[pid][f],'con_valor':filled[pid][f],
                    'formulario':f in declaradas,'referencias_codigo':refs[:12],'estado':estado})
                if seguro:out['limpieza_segura'].append({'proyecto_id':pid,'proyecto':nombre,'campo':f,'motivo':'Artefacto de importación vacío, sin declaraciones ni referencias'})
        def find(nombre):return next((pid for pid,n in nombres.items() if n==nombre),None)
        flm={pid for pid,n in nombres.items() if n.startswith('FLM - ')}
        indice_wo=defaultdict(set)
        wo_names={'numerowo','numerodewo','wonumber','taskid','taskno'}
        def wo_tokens(v):
            if isinstance(v,list):return [x for z in v for x in wo_tokens(z)]
            if not isinstance(v,(str,int)):return []
            return [norm(t) for t in re.split(r'[,;\n\r|]+',str(v)) if norm(t)]
        for pid in flm:
            for rid,key,d in rows[pid]:
                for valor in [key]+[v for k,v in d.items() if norm(k) in wo_names]:
                    for token in wo_tokens(valor):indice_wo[token].add((pid,rid))
        for nombre,candidatos in [('Rendicion',{'numerocmpmplm'}),('Cotizaciones',wo_names),('Combustible',wo_names)]:
            contador=Counter()
            for _,_,d in rows[find(nombre)]:
                tokens={t for k,v in d.items() if norm(k) in candidatos for t in wo_tokens(v)}
                if not tokens:contador['sin_referencia_wo']+=1;continue
                enlaces=set().union(*(indice_wo[t] for t in tokens))
                if not enlaces:contador['sin_coincidencia_local']+=1
                elif len(enlaces)==1:contador['coincidencia_unica']+=1
                else:contador['varias_coincidencias_revisar']+=1
            out['correlaciones'][nombre+'_a_WO']=dict(contador)
        por_proyecto=Counter()
        for _,_,d in rows[find('Dataper')]:por_proyecto[str(d.get('PROYECTO') or 'Sin proyecto')]+=1
        out['correlaciones']['personal_por_proyecto']=dict(por_proyecto)
        for nombre in ('Material','SITE','Generadores'):
            out['correlaciones'][nombre+'_proyecto']={'total':len(rows[find(nombre)]),'sin_proyecto':sum(not str(d.get('PROYECTO') or '').strip() for _,_,d in rows[find(nombre)])}
        nuc={r['id']:r['proyecto_id'] for r in c.execute('SELECT id,proyecto_id FROM nucleus_data')}
        cot=find('Cotizaciones')
        for tabla in ('refacturable_detalle','liquidacion_numero'):
            links=[r[0] for r in c.execute('SELECT origen_id FROM '+tabla)]
            out['correlaciones'][tabla]={'referencias':len(links),'sin_origen_actual':sum(x not in nuc for x in links),'origen_otro_modulo':sum(x in nuc and nuc[x]!=cot for x in links)}
        generadores=rows[find('Generadores')];qr={norm(d.get('QR ASIGNADO')) for _,_,d in generadores if d.get('QR ASIGNADO')}
        out['correlaciones']['combustible_a_generador']=dict(Counter('sin_qr' if not d.get('QR ASIGNADO') else 'encontrado' if norm(d['QR ASIGNADO']) in qr else 'sin_coincidencia_local' for _,_,d in rows[find('Combustible')]))
    return out


def informe(out):
    texto=['# Auditoría local de tablas y flujos','',out['alcance'],'',
        f"Integridad: {', '.join(out['integridad'])}. Relaciones foráneas rotas: {len(out['referencias_rotas'])}. JSON inválido: {len(out['errores_json'])}.",'',
        '## Inventario de tablas','','| Tabla | Registros | Columnas físicas | Relaciones declaradas |','|---|---:|---:|---:|']
    for nombre,t in out['tablas'].items():texto.append(f"| {nombre} | {t['filas']} | {len(t['columnas'])} | {len(t['relaciones'])} |")
    texto+=['','## Catálogos y columnas dinámicas','','| Proyecto / módulo | Registros | Campos | Campos sin valores |','|---|---:|---:|---:|']
    for n,p in out['proyectos'].items():texto.append(f"| {n} | {p['filas']} | {p['campos_totales']} | {p['campos_sin_valores']} |")
    texto+=['','Una columna vacía no se considera sobrante: puede ser un formulario, campo calculado o contrato de importación. Los campos sin referencias verificables se conservan para revisión. No se fusionan alias ni se eliminan columnas físicas por ausencia de datos.','','## Correlaciones sobre la copia disponible','']
    for nombre,contadores in out['correlaciones'].items():texto.append('- '+nombre+': '+', '.join(f'{k}={v}' for k,v in contadores.items())+'.')
    texto+=['','Una coincidencia por WO es una comprobación de claves, no una aprobación del registro. Una referencia sin coincidencia puede corresponder a datos externos no exportados, una WO pendiente o una clave histórica: no se inventan enlaces ni se eliminan filas.','','## Limpieza segura','',f"Artefactos vacíos sin datos, declaraciones ni referencias detectados: {len(out['limpieza_segura'])}.",'','Esta auditoría no modifica datos. No certifica adjuntos remotos, formularios Google/OneDrive, entregas de correo ni el aislamiento nuevo en todas las rutas nativas. Estos puntos necesitan comprobaciones específicas adicionales.']
    return '\n'.join(texto)+'\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--db',type=Path,required=True);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--salida',type=Path,required=True);parser.add_argument('--reporte',type=Path,required=True)
    args=parser.parse_args();args.salida.parent.mkdir(parents=True,exist_ok=True);args.reporte.parent.mkdir(parents=True,exist_ok=True)
    # Snapshot SQLite consistente antes de inspeccionar: incluye datos y configuraciones.
    backup=args.salida.with_suffix('.previo.db')
    with backup.open('xb'):pass
    with sqlite3.connect('file:'+args.db.resolve().as_posix()+'?mode=ro',uri=True) as src,sqlite3.connect(backup) as dst:src.backup(dst)
    out=audit(backup,args.root)
    with backup.open('rb') as f:out['respaldo_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    args.salida.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8');args.reporte.write_text(informe(out),encoding='utf-8')
    print(json.dumps({'tablas':len(out['tablas']),'fk_rotas':len(out['referencias_rotas']),'json_invalido':len(out['errores_json']),'limpieza_segura':len(out['limpieza_segura'])}))
