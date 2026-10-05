# -*- coding: utf-8 -*-
"""Replica la data de la BD cloud (Neon/Postgres) hacia la BD local SQLite.

Uso de PRUEBA (p. ej. para construir dashboards con datos reales del cloud):

    python replicate_neon_local.py --url "$DATABASE_URL" --dry-run   # solo contar
    python replicate_neon_local.py --url "$DATABASE_URL"             # replicar
    python replicate_neon_local.py --url "sqlite:///C:/ruta/origen.db"
    python replicate_neon_local.py --url "$DATABASE_URL" --proyectos "FLM - ENTEL,Cotizaciones"

Qué hace:
  * Por cada proyecto que exista en AMBAS bases (match por NOMBRE), reemplaza
    sus filas de `nucleus_data` y `app_config` en la BD local con las de origen.
  * Antes de escribir copia la BD local a `backups/neon_replica_<ts>.db`.
  * Sin `--url` ni variable DATABASE_URL en el entorno → aborta (no adivina
    credenciales).

Qué NO hace (a propósito, es una réplica ligera de prueba):
  * No copia usuarios, historial, notificaciones ni evidencias/fotos.
  * No crea proyectos que falten localmente (se listan como omitidos).
  * Las columnas `id` se regeneran (se omiten al insertar) para evitar
    colisiones de PK entre orígenes distintos.

Precaución: detén el servidor (`python app.py`) antes de replicar para evitar
bloqueos de SQLite durante la escritura.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TABLAS = ('nucleus_data', 'app_config')
SIN_ID = ('id',)  # columnas que nunca se copian (se autoasignan en local)


def conectar_origen(url):
    """Devuelve (conexion, marcador_param). Solo lectura sobre el origen."""
    if url.startswith('sqlite'):
        # sqlite:///C:/ruta/archivo.db  |  sqlite:////abs/ruta.db
        path = url.split('///', 1)[-1] if '///' in url else url.split(':', 1)[1]
        if path.startswith('/') and len(path) > 1 and path[1] == ':':  # /C:/...
            path = path[1:]
        if not os.path.exists(path):
            raise SystemExit('No existe la BD de origen: %s' % path)
        con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
        return con, '?'
    sys.path.insert(0, BASE_DIR)
    from config import _normalizar_db_url  # normaliza driver + sslmode
    import psycopg2
    con = psycopg2.connect(_normalizar_db_url(url))
    return con, '%s'


def columnas(con, tabla, ph):
    cur = con.cursor()
    cur.execute('SELECT * FROM %s WHERE 1=0' % tabla)
    return [d[0] for d in cur.description]


def adaptar(v):
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return str(v)  # datetime, Decimal, bool… → texto (las 4 columnas son TEXT)


def main():
    ap = argparse.ArgumentParser(description='Réplica de prueba Neon -> SQLite local')
    ap.add_argument('--url', default=os.environ.get('DATABASE_URL', ''),
                    help='URL de la BD de origen (DATABASE_URL de Neon o sqlite:///...)')
    ap.add_argument('--db', default=os.path.join(BASE_DIR, 'nucleus.db'),
                    help='BD local destino (default: nucleus.db)')
    ap.add_argument('--proyectos', default='',
                    help='Lista separada por comas de nombres de proyecto (default: todos)')
    ap.add_argument('--dry-run', action='store_true', help='Solo contar, no escribir')
    ap.add_argument('--no-backup', action='store_true', help='No copia de respaldo previa')
    a = ap.parse_args()

    if not a.url:
        raise SystemExit('Falta la BD de origen: usa --url o define DATABASE_URL en el entorno.')
    if not os.path.exists(a.db):
        raise SystemExit('No existe la BD local destino: %s' % a.db)

    origen, ph = conectar_origen(a.url)
    filtro = [n.strip().lower() for n in a.proyectos.split(',') if n.strip()]

    # Mapeo de proyectos por NOMBRE (los ids pueden diferir entre orígenes)
    def proyectos(con):
        cur = con.cursor()
        cur.execute('SELECT id, nombre FROM proyectos')
        return {str(n).strip().lower(): (i, n) for i, n in cur.fetchall()}

    src_proy = proyectos(origen)
    dst = sqlite3.connect(a.db, timeout=30)
    dst.execute('PRAGMA busy_timeout = 10000')
    dst_proy = proyectos(dst)

    pares = []
    for k, (sid, nombre) in sorted(src_proy.items(), key=lambda x: x[1][0]):
        if filtro and k not in filtro:
            continue
        if k in dst_proy:
            pares.append((sid, dst_proy[k][0], nombre))
        else:
            print('OMITIDO (no existe localmente): %s' % nombre)
    if filtro:
        faltan = [f for f in filtro if f not in src_proy]
        if faltan:
            print('OMITIDO (no existe en el origen): %s' % ', '.join(faltan))
    if not pares:
        raise SystemExit('Ningún proyecto para replicar.')

    # Conteos de origen
    origen_counts = {}
    for tabla in TABLAS:
        cur = origen.cursor()
        for sid, _, nombre in pares:
            cur.execute('SELECT COUNT(*) FROM %s WHERE %s=%s' % (tabla, 'proyecto_id', ph), (sid,))
            origen_counts[(tabla, nombre)] = cur.fetchone()[0]

    print('Origen : %s' % ('SQLite ' + a.url.split('///')[-1] if a.url.startswith('sqlite') else 'Neon/Postgres'))
    print('Destino: %s' % a.db)
    print('Proyectos: %s' % ', '.join(n for _, _, n in pares))

    if a.dry_run:
        print('\n[dry-run] filas de origen por tabla:')
        for (tabla, nombre), n in sorted(origen_counts.items()):
            print('  %-14s %-16s %6d' % (tabla, nombre, n))
        return

    # Respaldo previo
    if not a.no_backup:
        bak_dir = os.path.join(BASE_DIR, 'backups')
        os.makedirs(bak_dir, exist_ok=True)
        ts = time.strftime('%Y%m%d_%H%M%S')
        bak = os.path.join(bak_dir, 'neon_replica_%s.db' % ts)
        dst.close()
        shutil.copy2(a.db, bak)
        print('Respaldo local: %s' % bak)
        dst = sqlite3.connect(a.db, timeout=30)
        dst.execute('PRAGMA busy_timeout = 10000')

    total = 0
    try:
        for tabla in TABLAS:
            src_cols = columnas(origen, tabla, ph)
            dst_cols = set(columnas(dst, tabla, '?'))
            usar = [c for c in src_cols if c in dst_cols and c not in SIN_ID]
            fuera = [c for c in src_cols if c not in usar and c not in SIN_ID]
            if fuera:
                print('AVISO %s: columnas de origen ausentes en local, ignoradas: %s'
                      % (tabla, ', '.join(fuera)))
            insert_sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
                tabla, ','.join(usar), ','.join([ph] * len(usar)))
            cur_o = origen.cursor()
            for sid, did, nombre in pares:
                cur_o.execute('SELECT %s FROM %s WHERE proyecto_id=%s'
                              % (','.join(src_cols), tabla, ph), (sid,))
                filas = cur_o.fetchall()
                antes = dst.execute('SELECT COUNT(*) FROM %s WHERE proyecto_id=?'
                                    % tabla, (did,)).fetchone()[0]
                with dst:
                    dst.execute('DELETE FROM %s WHERE proyecto_id=?' % tabla, (did,))
                    idx = [src_cols.index(c) for c in usar]
                    dst.executemany(insert_sql,
                                    [tuple(adaptar(f[i]) for i in idx) for f in filas])
                despues = dst.execute('SELECT COUNT(*) FROM %s WHERE proyecto_id=?'
                                      % tabla, (did,)).fetchone()[0]
                total += despues
                print('%-14s %-16s %6d -> %6d filas (origen: %d)'
                      % (tabla, nombre, antes, despues, origen_counts.get((tabla, nombre), len(filas))))
        print('\nListo: %d filas escritas en %s' % (total, a.db))
        print('Reinicia el servidor si estaba corriendo para ver los datos en los dashboards.')
    finally:
        origen.close()
        dst.close()


if __name__ == '__main__':
    main()
