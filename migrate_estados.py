# -*- coding: utf-8 -*-
"""
MIGRACION SEGURA: "En proceso" → "En Aprobación" (pestaña 2. Cliente)
======================================================================
Pasos:
  1. python migrate_estados.py --dry-run   → muestra qué cambiaría SIN tocar nada
  2. python migrate_estados.py             → aplica los cambios reales

Lee DATABASE_URL del entorno o del archivo .env.
SOLO toca registros del proyecto 'Cotizaciones'.
"""

import os
import sys
import json
import argparse

# ─── carga .env local si existe ──────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# ─── args ─────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Migrar estados de Cotizaciones')
parser.add_argument('--dry-run', action='store_true',
                    help='Solo mostrar qué cambiaría, sin modificar nada')
# Estado origen (puede haber varios)
parser.add_argument('--from-estados', nargs='+',
                    default=['En proceso'],
                    help='Estado(s) a migrar (default: "En proceso")')
# Estado destino
parser.add_argument('--to-estado', default='En Aprobación',
                    help='Estado destino (default: "En Aprobación")')
args = parser.parse_args()

DRY = args.dry_run
FROM_ESTADOS = [e.strip().lower() for e in args.from_estados]
TO_ESTADO = args.to_estado.strip()

print('=' * 60)
print(f'  MODO: {"DRY-RUN (sin cambios)" if DRY else "*** PRODUCCIÓN — CAMBIOS REALES ***"}')
print(f'  Origen(s): {args.from_estados}')
print(f'  Destino:   {TO_ESTADO}')
print('=' * 60)

# ─── conexión ─────────────────────────────────────────────────────────────────
db_url = os.environ.get('DATABASE_URL', '')
if not db_url:
    print('ERROR: DATABASE_URL no encontrado. Pon DATABASE_URL en tu .env')
    sys.exit(1)

# psycopg2 / neon → reemplazar postgres:// → postgresql:// para SQLAlchemy
if db_url.startswith('postgres://'):
    db_url = 'postgresql://' + db_url[len('postgres://'):]

try:
    import psycopg2
    from urllib.parse import urlparse
    u = urlparse(db_url)
    conn = psycopg2.connect(
        host=u.hostname, port=u.port or 5432,
        dbname=u.path.lstrip('/'), user=u.username,
        password=u.password,
        sslmode='require'
    )
    cur = conn.cursor()
    print(f'  Conectado a: {u.hostname}/{u.path.lstrip("/")}')
except ImportError:
    # Fallback: SQLAlchemy directo
    from sqlalchemy import create_engine, text
    engine = create_engine(db_url)
    conn = None
    cur = None
    print('  (usando SQLAlchemy como fallback)')

print()

# ─── buscar proyecto Cotizaciones ─────────────────────────────────────────────
if conn:
    cur.execute("SELECT id, nombre FROM proyectos WHERE nombre ILIKE %s LIMIT 1", ('Cotizaciones',))
    row = cur.fetchone()
    if not row:
        print('ERROR: No se encontró el proyecto "Cotizaciones" en la BD')
        conn.close()
        sys.exit(1)
    proy_id, proy_nombre = row
    print(f'  Proyecto: {proy_nombre} (id={proy_id})')

    # ─── escanear registros ──────────────────────────────────────────────────
    cur.execute("SELECT id, key_value, data_json FROM nucleus_data WHERE proyecto_id = %s", (proy_id,))
    rows = cur.fetchall()
else:
    with engine.connect() as ec:
        row = ec.execute(text("SELECT id, nombre FROM proyectos WHERE nombre ILIKE 'Cotizaciones' LIMIT 1")).fetchone()
        if not row:
            print('ERROR: No se encontró el proyecto "Cotizaciones"')
            sys.exit(1)
        proy_id, proy_nombre = row[0], row[1]
        print(f'  Proyecto: {proy_nombre} (id={proy_id})')
        rows_r = ec.execute(text("SELECT id, key_value, data_json FROM nucleus_data WHERE proyecto_id = :pid"), {'pid': proy_id}).fetchall()
        rows = [(r[0], r[1], r[2]) for r in rows_r]

print(f'  Total registros en Cotizaciones: {len(rows)}')
print()

# ─── identificar afectados ────────────────────────────────────────────────────
afectados = []
for rec_id, key_val, data_json_raw in rows:
    try:
        d = json.loads(data_json_raw)
    except Exception:
        continue
    estado_actual = str(d.get('ESTADO COTIZACION', '') or '').strip()
    if estado_actual.lower() in FROM_ESTADOS:
        afectados.append((rec_id, key_val, estado_actual, d))

print(f'  Registros a migrar: {len(afectados)}')
print()

if not afectados:
    print('  Nada que migrar. Verifica los estados con --from-estados')
    if conn:
        conn.close()
    sys.exit(0)

# ─── preview (primeros 10) ────────────────────────────────────────────────────
print('  Preview (primeros 10):')
for rec_id, key_val, estado_actual, d in afectados[:10]:
    print(f'    [{key_val}] "{estado_actual}" → "{TO_ESTADO}"')
if len(afectados) > 10:
    print(f'    ... y {len(afectados)-10} más')
print()

if DRY:
    print('  DRY-RUN completado — no se realizaron cambios.')
    print('  Para aplicar: python migrate_estados.py')
    if conn:
        conn.close()
    sys.exit(0)

# ─── aplicar cambios ──────────────────────────────────────────────────────────
confirm = input(f'  ¿Confirmar migración de {len(afectados)} registros? (escribe "SI" para continuar): ')
if confirm.strip().upper() != 'SI':
    print('  Cancelado.')
    if conn:
        conn.close()
    sys.exit(0)

ok = 0
err = 0
for rec_id, key_val, estado_actual, d in afectados:
    d['ESTADO COTIZACION'] = TO_ESTADO
    nuevo_json = json.dumps(d, ensure_ascii=False)
    try:
        if conn:
            cur.execute("UPDATE nucleus_data SET data_json = %s WHERE id = %s", (nuevo_json, rec_id))
        else:
            with engine.connect() as ec:
                ec.execute(text("UPDATE nucleus_data SET data_json = :j WHERE id = :id"), {'j': nuevo_json, 'id': rec_id})
                ec.commit()
        ok += 1
    except Exception as e:
        print(f'  ERROR en {key_val}: {e}')
        err += 1

if conn:
    conn.commit()
    conn.close()

print()
print(f'  ✅ Migrados exitosamente: {ok}')
if err:
    print(f'  ❌ Errores: {err}')
print('  Recarga la app para ver los cambios.')
