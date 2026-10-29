"""Homologa exclusivamente el nombre de beneficiario por DNI. Sin --apply ensaya.

Respalda antes/después bajo el bloqueo y permite --revert del archivo de lote.
Nunca cambia DNI, pagos, estados, adjuntos ni claves de registros.
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
import unicodedata
import re

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.rendicion_homologacion import dni, nombre_completo, aplicar


def campo(d, claves):
    def normal(v):
        return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().lower())
    m={normal(k):v for k,v in d.items()}
    return next((str(m[normal(k)]).strip() for k in claves if m.get(normal(k)) is not None and str(m[normal(k)]).strip()), '')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--connection-file',required=True)
    ap.add_argument('--backup-dir',required=True)
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--revert')
    args=ap.parse_args()
    config=json.loads(Path(args.connection_file).read_text(encoding='utf-8'))
    dest=Path(args.backup_dir); dest.mkdir(parents=True,exist_ok=True)
    path=dest/('lote-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with psycopg2.connect(config['database_url'],connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('LOCK TABLE nucleus_data IN SHARE ROW EXCLUSIVE MODE')
            cur.execute("SELECT id,nombre FROM proyectos WHERE nombre IN ('Rendicion','Dataper')")
            proyectos={n:i for i,n in cur.fetchall()}; pid=proyectos['Rendicion']
            cur.execute("SELECT valor FROM app_config WHERE proyecto_id=%s AND clave='rendicion_nombres_homologados' FOR UPDATE",(pid,))
            cfg=cur.fetchone(); anterior_cfg=cfg[0] if cfg else None
            cur.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id',(pid,))
            rows=cur.fetchall(); originales={i:json.loads(raw) for i,k,raw in rows}
            if args.revert:
                lote=json.loads(Path(args.revert).read_text(encoding='utf-8'))
                if lote['branch_id']!=config['branch_id'] or anterior_cfg!=lote['catalogo_nuevo']:
                    raise ValueError('El origen o catálogo cambió después del lote.')
                cambios=[]
                for entry in lote['cambios']:
                    actual=originales[entry['id']]
                    for key in ('Técnico beneficiario','_BENEFICIARIO_HOMOLOGACION'):
                        if actual.get(key)!=entry['despues'].get(key):
                            raise ValueError('Una identidad fue corregida después del lote; revisar antes de revertir.')
                    nuevo=dict(actual)
                    for key in ('Técnico beneficiario','_BENEFICIARIO_HOMOLOGACION'):
                        if key in entry['antes']: nuevo[key]=entry['antes'][key]
                        else: nuevo.pop(key,None)
                    cambios.append({'id':entry['id'],'key':entry['key'],'antes':actual,'despues':nuevo})
                catalogo_nuevo=lote['catalogo_anterior']
                resumen={'reversion':True}
            else:
                cur.execute('SELECT data_json FROM nucleus_data WHERE proyecto_id=%s',(proyectos['Dataper'],))
                personal=defaultdict(list); fuentes=defaultdict(list)
                for (raw,) in cur.fetchall():
                    d=json.loads(raw); doc=dni(campo(d,['DOCUMENTO','DNI','NUMERO DE DOCUMENTO','NRO DOCUMENTO']))
                    if doc: personal[doc].append(campo(d,['TECNICO','NOMBRE DEL TECNICO','NOMBRE COMPLETO','APELLIDOS Y NOMBRES']))
                for d in originales.values():
                    doc=dni(campo(d,['Documento del beneficiario','DOCUMENTO','DNI','Numero de documento','Documento de identidad']))
                    if doc: fuentes[doc].append(campo(d,['Técnico beneficiario','TECNICO','Nombre del beneficiario']))
                catalogo={}; pendientes=0
                for doc,nombres in fuentes.items():
                    # Personal es la fuente principal. No promover texto libre
                    # contradictorio o ubicaciones a identidad oficial.
                    nombre=nombre_completo(personal.get(doc) or nombres)
                    if nombre: catalogo[doc]={'nombre':nombre,'fuente':'Personal' if personal.get(doc) else 'Rendicion: variantes compatibles por DNI'}
                    else: pendientes+=1
                cambios=[]
                for i,key,raw in rows:
                    antes=originales[i]; despues=aplicar(dict(antes),catalogo)
                    if despues!=antes: cambios.append({'id':i,'key':key,'antes':antes,'despues':despues})
                catalogo_nuevo=json.dumps(catalogo,ensure_ascii=False,sort_keys=True)
                resumen={'documentos_homologados':len(catalogo),'documentos_conflictivos_pendientes':pendientes,
                         'filas_sin_dni_valido':sum(not dni(campo(d,['Documento del beneficiario','DOCUMENTO','DNI','Numero de documento','Documento de identidad'])) for d in originales.values())}
            lote={'branch_id':config['branch_id'],'catalogo_anterior':anterior_cfg,'catalogo_nuevo':catalogo_nuevo,
                  'cambios':cambios,'filas_rendicion':len(rows),'resumen':resumen,'aplicado':args.apply}
            with path.open('x',encoding='utf-8') as f: json.dump(lote,f,ensure_ascii=False,indent=2)
            permitidos={'Técnico beneficiario','_BENEFICIARIO_HOMOLOGACION'}
            updates=[]; auditoria=[]
            for entry in cambios:
                assert {k:v for k,v in entry['antes'].items() if k not in permitidos}=={k:v for k,v in entry['despues'].items() if k not in permitidos}
                updates.append((entry['id'],json.dumps(entry['despues'],ensure_ascii=False)))
                auditoria.append((pid,'homologacion-dni',entry['key'],'Técnico beneficiario',entry['antes'].get('Técnico beneficiario',''),entry['despues'].get('Técnico beneficiario',''),datetime.now(timezone.utc).replace(tzinfo=None)))
            if updates:
                execute_values(cur, f'UPDATE nucleus_data n SET data_json=v.raw FROM (VALUES %s) AS v(id,raw) WHERE n.id=v.id AND n.proyecto_id={int(pid)}',updates,page_size=len(updates))
                assert cur.rowcount==len(updates)
                execute_values(cur,'INSERT INTO historial_cambios(proyecto_id,username,key_value,campo_modificado,valor_anterior,valor_nuevo,fecha) VALUES %s',auditoria,page_size=len(auditoria))
            if catalogo_nuevo is None:
                cur.execute("DELETE FROM app_config WHERE proyecto_id=%s AND clave='rendicion_nombres_homologados'",(pid,))
            else:
                cur.execute("INSERT INTO app_config(proyecto_id,clave,valor) VALUES(%s,'rendicion_nombres_homologados',%s) ON CONFLICT(proyecto_id,clave) DO UPDATE SET valor=excluded.valor",(pid,catalogo_nuevo))
            cur.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id',(pid,))
            actual=cur.fetchall(); assert len(actual)==len(rows)
            esperado={e['id']:e['despues'] for e in cambios}
            for i,key,raw in actual:
                assert json.loads(raw)==esperado.get(i,originales[i])
            if args.apply: conn.commit()
            else: conn.rollback()
    print(json.dumps({'aplicado':args.apply,'filas':len(rows),'nombres_modificados':len(cambios),
                      'lote':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**resumen},ensure_ascii=True))


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('OPERACION_NO_COMPLETADA: '+type(error).__name__,file=sys.stderr); raise SystemExit(1)
