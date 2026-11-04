"""Carga explícita de los Excel FLM: respalda, añade columnas y conserva gestión.

Sin --apply ensaya la misma transacción y hace rollback. No elimina ausentes,
no consolida, no cambia identificadores de filas existentes ni toca otros módulos.
La conexión se recibe solo mediante NUCLEUS_IMPORT_URL_B64 y no se imprime.
"""
import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


PROTEGIDOS = {
    'SERVICIO', 'CIUDAD', 'TECNICO', 'CONTRATA', 'INICIO EJECUCION', 'FIN EJECUCION',
    'MOTIVO DE AVERÍA', 'MOTIVO DE AVERIA', 'SOLUCIÓN', 'SOLUCION', 'LATITUD', 'LONGITUD',
    'SE INSTALÓ MUFAS', 'SE INSTALO MUFAS', 'LATITUD MUFAS', 'LONGITUD MUFAS',
    'UBICACIÓN DE MUFAS', 'UBICACION DE MUFAS', 'SISTEMAS', 'SISTEMA', 'MATERIALES',
    'Fecha de creación (WO Creation date)', 'Nombre de Site', 'Autin TT',
    'Departamento', 'Fault Level', 'Estado de la tarea (WO State)',
    'Prioridad del Site', 'Provincia', 'Distrito',
}


def leer(path, key):
    df = pd.read_excel(path, dtype=str).fillna('')
    df.columns = [str(c).strip().replace('.', '_') for c in df.columns]
    if len(df.columns) != len(set(df.columns)):
        raise ValueError('Hay encabezados repetidos: ' + path.name)
    if key not in df.columns:
        raise ValueError(f'Falta {key} en {path.name}')
    rows = []
    seen = set()
    for data in df.to_dict('records'):
        if not any(str(v).strip() for v in data.values()):
            continue
        ident = str(data[key]).strip()
        if not ident or ident in seen or len(ident) > 100:
            raise ValueError(f'Clave vacía, repetida o inválida en {path.name}')
        if not ident.startswith(('CM-', 'PM-', 'PLM-')):
            raise ValueError(f'Identificador no reconocido en {path.name}')
        data[key] = ident
        seen.add(ident)
        rows.append(data)
    return list(df.columns), rows


def combinar(actual, fuente, manuales):
    protegido = {c.casefold() for c in PROTEGIDOS} | {str(c).casefold() for c in manuales}
    result = dict(actual)
    for k, v in fuente.items():
        if k.startswith('_'):
            raise ValueError('El Excel no puede contener metadatos internos.')
        if k in actual and k.casefold() in protegido:
            continue
        result[k] = v
    assert all(result[k] == v for k, v in actual.items() if k not in fuente)
    return result


def ejecutar(con, entradas, backup_dir):
    summaries = []
    with con.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='15s'")
        cur.execute("SET LOCAL statement_timeout='180s'")
        for nombre, key, path, esperado_pid in entradas:
            headers, source = leer(path, key)
            from services.importacion_estados import cancelado
            ignorados_cancelados = sum(cancelado(row, nombre) for row in source)
            source = [row for row in source if not cancelado(row, nombre)]
            cur.execute('SELECT id FROM proyectos WHERE nombre=%s', (nombre,))
            found = cur.fetchone()
            if not found or found[0] != esperado_pid:
                raise ValueError('El módulo no coincide con el destino confirmado: ' + nombre)
            pid = found[0]
            cur.execute('SELECT id,clave,valor FROM app_config WHERE proyecto_id=%s ORDER BY id FOR UPDATE', (pid,))
            config_rows = cur.fetchall()
            config = {c: (i,v) for i,c,v in config_rows}
            cur.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id FOR UPDATE', (pid,))
            old_rows = cur.fetchall()
            current = {k:(i,raw) for i,k,raw in old_rows}
            if len(current) != len(old_rows):
                raise ValueError('El módulo tiene claves duplicadas.')
            backup = {'modulo':nombre,'pid':pid,'archivo':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'config':config_rows,'filas':old_rows}
            (backup_dir / (nombre.replace(' ','_')+'.json')).write_text(json.dumps(backup,ensure_ascii=False),encoding='utf-8')
            manuales = [c['nombre'] for c in json.loads(config.get('manual_columns',(0,'[]'))[1])]
            changed, added, histories = [], [], []
            expected = {}
            for data in source:
                ident = data[key]
                if ident in current:
                    i,raw=current[ident]; old=json.loads(raw)
                    new=combinar(old,data,manuales)
                    if new != old:
                        changed.append((i,json.dumps(new,ensure_ascii=False)))
                        histories.append((pid,ident,raw,datetime.now(timezone.utc).replace(tzinfo=None)))
                    expected[ident]=new
                else:
                    added.append((pid,ident,json.dumps(data,ensure_ascii=False)))
                    expected[ident]=data
            if histories:
                execute_values(cur,'INSERT INTO nucleus_history(proyecto_id,key_value,data_json,fecha_consolidado) VALUES %s',histories,page_size=200)
            if changed:
                execute_values(cur,'UPDATE nucleus_data n SET data_json=v.raw FROM (VALUES %s) v(id,raw) WHERE n.id=v.id',changed,page_size=200)
            if added:
                execute_values(cur,'INSERT INTO nucleus_data(proyecto_id,key_value,data_json) VALUES %s',added,page_size=200)
            schema = json.loads(config.get('app_schema',(0,'[]'))[1])
            new_schema = list(dict.fromkeys([key]+headers+schema))
            for setting,value in [('primary_key',key),('app_schema',json.dumps(new_schema,ensure_ascii=False))]:
                if setting in config:
                    cur.execute('UPDATE app_config SET valor=%s WHERE id=%s',(value,config[setting][0]))
                else:
                    cur.execute('INSERT INTO app_config(proyecto_id,clave,valor) VALUES(%s,%s,%s)',(pid,setting,value))
            cur.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s',(pid,))
            actual = {k:(i,raw) for i,k,raw in cur.fetchall()}
            assert len(actual)==len(old_rows)+len(added)
            for ident,data in expected.items():
                assert json.loads(actual[ident][1])==data
            for ident,(i,raw) in current.items():
                assert actual[ident][0]==i
                if ident not in expected:
                    assert actual[ident][1]==raw
            # La fuente manda solo sobre sus columnas; la gestión y evidencia no cambian.
            for ident in set(current) & set(expected):
                before=json.loads(current[ident][1]); after=expected[ident]
                for field,value in before.items():
                    if field.casefold() in {c.casefold() for c in PROTEGIDOS}|{c.casefold() for c in manuales} or field.startswith('_'):
                        assert after[field]==value
            summaries.append(dict(modulo=nombre,columnas_excel=len(headers),columnas_agregadas=len(set(headers)-set(schema)),
                                  filas_excel=len(source),anteriores=len(old_rows),agregados=len(added),
                                  actualizados=len(changed),sin_cambio=len(source)-len(added)-len(changed),
                                  total=len(actual),clave=key,ignorados_cancelados=ignorados_cancelados))
    return summaries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--carpeta',type=Path,required=True)
    parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    args.backup_dir.mkdir(parents=True,exist_ok=True)
    url=base64.b64decode(os.environ['NUCLEUS_IMPORT_URL_B64']).decode()
    with psycopg2.connect(url,connect_timeout=20) as con:
        result=ejecutar(con,[('FLM - CLARO','Ticket Id',args.carpeta/'WOs All Claro.xlsx',17),
                            ('FLM - INTEGRATEL','Task Id',args.carpeta/'WOs All Integratel.xlsx',15)],args.backup_dir)
        if args.apply: con.commit()
        else: con.rollback()
    print(json.dumps({'aplicado':args.apply,'resultados':result},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
