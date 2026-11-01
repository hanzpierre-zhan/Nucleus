"""Añade SUPERVISOR vacío al maestro sin inventar asignaciones; reversión selectiva."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-file', required=True)
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--revert')
    args = parser.parse_args()
    cfg = json.loads(Path(args.connection_file).read_text(encoding='utf8'))
    folder = Path(args.backup_dir); folder.mkdir(parents=True, exist_ok=True)
    lote = {'branch_id': cfg['branch_id'], 'cambios': [], 'config': []}
    with psycopg2.connect(cfg['database_url'], connect_timeout=15) as con:
        with con.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('LOCK TABLE nucleus_data,app_config IN SHARE ROW EXCLUSIVE MODE')
            cur.execute("SELECT id FROM proyectos WHERE nombre='Dataper'"); pid = cur.fetchone()[0]
            cur.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id', (pid,))
            rows = cur.fetchall(); lote['respaldo_filas'] = rows
            cur.execute("SELECT id,valor FROM app_config WHERE proyecto_id=%s AND clave='manual_columns'", (pid,))
            cid, anterior = cur.fetchone()
            columnas = json.loads(anterior)
            if args.revert:
                original = json.loads(Path(args.revert).read_text(encoding='utf8'))
                assert original['branch_id'] == cfg['branch_id']
                por_id = {r[0]: r for r in rows}
                for entry in original['cambios']:
                    i, key, raw = por_id[entry['id']]; d = json.loads(raw)
                    assert d.get('SUPERVISOR') == '', 'Supervisor fue completado después; no sobrescribir'
                    nuevo = dict(d); nuevo.pop('SUPERVISOR')
                    lote['cambios'].append({'id':i,'key':key,'antes':d,'despues':nuevo})
                if original['config']:
                    assert anterior == original['config'][0]['despues'], 'La configuración cambió después'
                    lote['config'].append({'id':cid,'antes':anterior,'despues':original['config'][0]['antes']})
            else:
                for i,key,raw in rows:
                    d = json.loads(raw)
                    if 'SUPERVISOR' not in d:
                        lote['cambios'].append({'id':i,'key':key,'antes':d,'despues':{**d,'SUPERVISOR':''}})
                if not any(c.get('nombre') == 'SUPERVISOR' for c in columnas):
                    columnas.append({'nombre':'SUPERVISOR','tipo':'texto','opciones':[]})
                    lote['config'].append({'id':cid,'antes':anterior,'despues':json.dumps(columnas,ensure_ascii=False)})
            archivo = folder / ('lote-supervisor-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            archivo.write_text(json.dumps(lote,ensure_ascii=False,indent=2),encoding='utf8')
            cambios = lote['cambios']
            if cambios:
                execute_values(cur,'UPDATE nucleus_data n SET data_json=v.raw FROM (VALUES %s) v(id,raw) WHERE n.id=v.id',
                    [(e['id'],json.dumps(e['despues'],ensure_ascii=False)) for e in cambios],page_size=len(cambios))
                assert cur.rowcount == len(cambios)
                execute_values(cur,'INSERT INTO historial_cambios(proyecto_id,username,key_value,campo_modificado,valor_anterior,valor_nuevo,fecha) VALUES %s',
                    [(pid,'supervisor-dataper',e['key'],'SUPERVISOR','(ausente)' if not args.revert else '', '' if not args.revert else '(ausente)',datetime.now(timezone.utc).replace(tzinfo=None)) for e in cambios])
            for e in lote['config']:
                cur.execute('UPDATE app_config SET valor=%s WHERE id=%s',(e['despues'],e['id']))
            cur.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id',(pid,))
            expected = {e['id']:e['despues'] for e in cambios}
            actual = cur.fetchall(); assert len(actual) == len(rows)
            for (i,key,raw), (i0,key0,raw0) in zip(actual, rows):
                assert (i,key) == (i0,key0)
                if i in expected:
                    assert json.loads(raw) == expected[i]
                    assert {k:v for k,v in json.loads(raw).items() if k!='SUPERVISOR'} == {k:v for k,v in json.loads(raw0).items() if k!='SUPERVISOR'}
                else: assert raw == raw0
            if args.apply: con.commit()
            else: con.rollback()
    print(json.dumps({'aplicado':args.apply,'filas':len(rows),'columna_agregada':len(cambios),'configuracion':len(lote['config']),'lote':str(archivo)},ensure_ascii=True))


if __name__ == '__main__':
    main()
