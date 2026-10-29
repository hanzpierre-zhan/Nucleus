"""Corrige solo categorías inválidas. Respaldo, auditoría y reversión por lote."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.rendicion_gastos import CAMPO, META, clasificar, valido


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-file', required=True)
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--revert')
    args = parser.parse_args()
    config = json.loads(Path(args.connection_file).read_text(encoding='utf-8'))
    carpeta = Path(args.backup_dir); carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / ('lote-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with psycopg2.connect(config['database_url'], connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='10s'")
            cursor.execute('LOCK TABLE nucleus_data IN SHARE ROW EXCLUSIVE MODE')
            cursor.execute("SELECT id FROM proyectos WHERE nombre='Rendicion'")
            pid = cursor.fetchone()[0]
            cursor.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id', (pid,))
            filas = cursor.fetchall()
            originales = {i: json.loads(raw) for i, key, raw in filas}
            cambios = []
            if args.revert:
                lote = json.loads(Path(args.revert).read_text(encoding='utf-8'))
                if lote['branch_id'] != config['branch_id']:
                    raise ValueError('El lote pertenece a otra rama.')
                for entry in lote['cambios']:
                    actual = originales[entry['id']]
                    if any(actual.get(k) != entry['despues'].get(k) for k in (CAMPO, META)):
                        raise ValueError('Categoría corregida después del lote: requiere revisión.')
                    nuevo = dict(actual)
                    for k in (CAMPO, META):
                        if k in entry['antes']: nuevo[k] = entry['antes'][k]
                        else: nuevo.pop(k, None)
                    cambios.append({'id':entry['id'], 'key':entry['key'], 'antes':actual, 'despues':nuevo})
            else:
                for i, key, raw in filas:
                    antes = originales[i]; despues = clasificar(antes)
                    if despues != antes:
                        assert CAMPO in antes and not valido(antes[CAMPO])
                        assert valido(despues[CAMPO])
                        cambios.append({'id':i, 'key':key, 'antes':antes, 'despues':despues})
            lote = {'branch_id': config['branch_id'], 'aplicado':args.apply, 'reversion':bool(args.revert),
                    'respaldo_filas': [{'id':i,'key':key,'data_json':raw} for i,key,raw in filas], 'cambios':cambios}
            with archivo.open('x', encoding='utf-8') as f:
                json.dump(lote, f, ensure_ascii=False, indent=2)
            updates, historial = [], []
            for entry in cambios:
                assert {k:v for k,v in entry['antes'].items() if k not in (CAMPO,META)} == {k:v for k,v in entry['despues'].items() if k not in (CAMPO,META)}
                updates.append((entry['id'], json.dumps(entry['despues'], ensure_ascii=False)))
                historial.append((pid,'homologacion-gastos',entry['key'],CAMPO,
                    str(entry['antes'].get(CAMPO) or ''), str(entry['despues'].get(CAMPO) or ''),
                    datetime.now(timezone.utc).replace(tzinfo=None)))
            if updates:
                execute_values(cursor, f'UPDATE nucleus_data n SET data_json=v.raw FROM (VALUES %s) AS v(id,raw) WHERE n.id=v.id AND n.proyecto_id={int(pid)}', updates, page_size=len(updates))
                assert cursor.rowcount == len(updates)
                execute_values(cursor, 'INSERT INTO historial_cambios(proyecto_id,username,key_value,campo_modificado,valor_anterior,valor_nuevo,fecha) VALUES %s', historial, page_size=len(historial))
            cursor.execute('SELECT id,key_value,data_json FROM nucleus_data WHERE proyecto_id=%s ORDER BY id', (pid,))
            actuales = cursor.fetchall()
            assert len(actuales) == len(filas)
            esperados = {e['id']:e['despues'] for e in cambios}
            originales_raw = {i:(key,raw) for i,key,raw in filas}
            for i,key,raw in actuales:
                assert key == originales_raw[i][0]
                assert json.loads(raw) == esperados.get(i, originales[i])
                if i not in esperados: assert raw == originales_raw[i][1]
            if args.apply: connection.commit()
            else: connection.rollback()
    resumen = {'aplicado':args.apply,'filas':len(filas),'corregidos':len(cambios),'filas_intactas':len(filas)-len(cambios),
        'validos_conservados':sum(CAMPO in d and valido(d[CAMPO]) for d in originales.values()),
        'destinos':dict(Counter(e['despues'].get(CAMPO) for e in cambios)),
        'requieren_revision':sum(bool(e['despues'].get(META,{}).get('requiere_revision')) for e in cambios),
        'lote':str(archivo.resolve()),'sha256':hashlib.sha256(archivo.read_bytes()).hexdigest()}
    archivo.with_suffix('.resultado.json').write_text(json.dumps(resumen,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(resumen,ensure_ascii=True))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('OPERACION_NO_COMPLETADA: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
