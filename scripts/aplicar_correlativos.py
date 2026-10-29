"""Conciliación puntual con respaldo, comprobaciones e índices en una transacción.

Usar --apply solo tras verificar en una rama de pruebas. El archivo de conexión
es privado (ignorado por Git), con database_url y branch_id. Sin --apply revierte.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-file', required=True)
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--allow-production', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.connection_file).read_text(encoding='utf-8'))
    if config['branch_id'] == 'br-spring-tree-axi7369a' and not args.allow_production:
        raise SystemExit('Producción requiere --allow-production explícito.')
    root = Path(__file__).resolve().parents[1]
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / ('antes-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    sql = (root / 'scripts/sql/cotizacion_correlativos_20261029.sql').read_text(encoding='utf-8')
    with psycopg2.connect(config['database_url'], connect_timeout=15) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SET LOCAL lock_timeout='10s'")
            cursor.execute("SELECT id FROM proyectos WHERE nombre='Cotizaciones'")
            pid = cursor.fetchone()['id']
            cursor.execute("SELECT 1 FROM app_config WHERE proyecto_id=%s AND clave='cotizacion_next_seq' FOR UPDATE", (pid,))
            cursor.execute('LOCK TABLE nucleus_data IN SHARE ROW EXCLUSIVE MODE')
            cursor.execute('SELECT * FROM nucleus_data WHERE proyecto_id=%s ORDER BY id', (pid,))
            before = [dict(row) for row in cursor.fetchall()]
            cursor.execute('SELECT * FROM app_config WHERE proyecto_id=%s ORDER BY id', (pid,))
            configs = [dict(row) for row in cursor.fetchall()]
            backup.write_text(json.dumps({'branch_id': config['branch_id'], 'nucleus_data': before,
                                          'app_config': configs}, ensure_ascii=False, indent=2), encoding='utf-8')
            cursor.execute(sql)
            changes = [dict(row) for row in cursor.fetchall()]
            cursor.execute('SELECT * FROM nucleus_data WHERE proyecto_id=%s ORDER BY id', (pid,))
            after = [dict(row) for row in cursor.fetchall()]
            assert len(before) == len(after)
            allowed = {'N° COTIZACION', 'N° ORDEN', '_NUMERACION_CONCILIADA', '_ORDEN_CONCILIADA'}
            modified = 0
            for old, new in zip(before, after):
                assert (old['id'], old['key_value']) == (new['id'], new['key_value'])
                old_data, new_data = json.loads(old['data_json']), json.loads(new['data_json'])
                assert {k: v for k, v in old_data.items() if k not in allowed} == {k: v for k, v in new_data.items() if k not in allowed}
                if old_data != new_data:
                    modified += 1
                else:
                    assert old['data_json'] == new['data_json']
            cursor.execute("SELECT campo,count(*) AS cantidad FROM numeracion_cambios GROUP BY campo ORDER BY campo")
            assert [dict(row) for row in cursor.fetchall()] == [
                {'campo': row['campo'], 'cantidad': row['cambios']} for row in changes]
            cursor.execute("SELECT count(*) AS grupos FROM (SELECT data_json::jsonb->>'N° ORDEN' FROM nucleus_data WHERE proyecto_id=%s AND COALESCE(data_json::jsonb->>'N° ORDEN','')<>'' GROUP BY 1 HAVING count(*)>1) t", (pid,))
            assert cursor.fetchone()['grupos'] == 0
            cursor.execute('SELECT id,clave,campo,anterior,nuevo FROM numeracion_cambios ORDER BY id,campo')
            mapping = [dict(row) for row in cursor.fetchall()]
            outcome = {'branch_id': config['branch_id'], 'aplicado': args.apply, 'filas_totales': len(before),
                       'filas_modificadas': modified, 'filas_intactas': len(before) - modified,
                       'cambios': changes, 'referencias_y_datos_comerciales_intactos': True,
                       'backup': str(backup), 'backup_sha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
                       'mapeo': mapping}
            if args.apply:
                connection.commit()
            else:
                connection.rollback()
            result = backup.with_name(backup.stem.replace('antes-', 'resultado-') + '.json')
            result.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({key: value for key, value in outcome.items() if key != 'mapeo'}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Evitar que las excepciones de conexión expongan detalles privados.
        print('FALLO: transaccion revertida; tipo=' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
