"""Auditoria puntual: que valores reales tiene ESTADO COTIZACION en la BD.

Responde: de donde salio 'Pendiente de Aprobacion' y como se reparte de verdad.
Solo lee. No modifica nada.
"""
import json
import sqlite3
from collections import Counter

DB = r'C:\Mega\Proyect\Nucleus\nucleus.db'

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

proy = cur.execute(
    "SELECT id, nombre FROM proyectos WHERE lower(nombre) = lower('Cotizaciones')"
).fetchall()
if not proy:
    raise SystemExit('No existe el proyecto Cotizaciones')
pid = proy[0]['id']
print('PROYECTO: %s (id=%s)' % (proy[0]['nombre'], pid))

# ── 1. Inventario real de estados ────────────────────────────────────────────
filas = cur.execute(
    "SELECT id, key_value, data_json FROM nucleus_data WHERE proyecto_id = ?", (pid,)
).fetchall()

MAP = {
    'atendido': 'atendido', 'validado': 'atendido',
    'cotizado': 'cliente', 'en aprobación': 'cliente', 'en aprobacion': 'cliente',
    'aprobado': 'sustentar', 'sustentar': 'sustentar',
    'cancelado': 'cancelado', 'anulado': 'cancelado', 'anulada': 'cancelado',
}
UI = {
    'cancelado': 'cancelado', 'anulado': 'cancelado', 'anulada': 'cancelado',
    'atendido': 'atendido', 'validado': 'atendido',
    'aprobado': 'sustentar', 'sustentar': 'sustentar',
    'pdt. cotización': 'registro', 'pdt. cotizacion': 'registro',
}

crudo = Counter()
pestania_be = Counter()
pestania_ui = Counter()
fuera_de_mapa = Counter()

for f in filas:
    try:
        d = json.loads(f['data_json'] or '{}')
    except Exception:
        d = {}
    est = str(d.get('ESTADO COTIZACION') or '').strip()
    crudo[est] += 1
    k = est.lower()
    be = MAP.get(k, 'registro')
    ui = UI.get(k, 'cliente')
    pestania_be[be] += 1
    pestania_ui[ui] += 1
    if k not in MAP and k not in UI:
        fuera_de_mapa[est] += 1

print('\nTOTAL REGISTROS: %d' % len(filas))

print('\n=== ESTADOS CRUDOS GUARDADOS (valor -> cuantos) ===')
for est, n in crudo.most_common():
    etiqueta = est if est else '(vacio)'
    marca = ''
    if est.lower() not in MAP and est.lower() not in UI:
        marca = '   <-- NO ESTA EN NINGUN MAPA'
    print('  %-32s %4d%s' % (etiqueta, n, marca))

print('\n=== A QUE PESTANIA CAE CADA UNO (lo que ve el usuario vs backend) ===')
print('  %-32s %-10s %-10s' % ('ESTADO', 'UI', 'BACKEND'))
for est, n in crudo.most_common():
    k = est.lower()
    print('  %-32s %-10s %-10s  (%d filas)' % (
        est if est else '(vacio)', UI.get(k, 'cliente'), MAP.get(k, 'registro'), n))

print('\n=== REPARTO DE FILAS POR PESTANIA ===')
print('  UI     :', dict(pestania_ui))
print('  BACKEND:', dict(pestania_be))

print('\n=== VALORES QUE NINGUN MAPA CONOCE (caen por fallback) ===')
for est, n in fuera_de_mapa.most_common():
    print('  "%s" -> %d filas' % (est if est else '(vacio)', n))

# ── 2. El registro de la captura ─────────────────────────────────────────────
print('\n=== REGISTRO HW-2026-0000209 ===')
for f in filas:
    if 'HW-2026-0000209' in str(f['key_value']):
        d = json.loads(f['data_json'] or '{}')
        est = str(d.get('ESTADO COTIZACION') or '')
        print('  key=%s  ESTADO COTIZACION=%r' % (f['key_value'], est))

# ── 3. Opciones configuradas de la columna (que se puede elegir) ─────────────
print('\n=== COLUMNA ESTADO COTIZACION: opciones configuradas ===')
mc = cur.execute(
    "SELECT valor FROM app_config WHERE proyecto_id = ? AND clave = 'manual_columns'", (pid,)
).fetchone()
if not mc:
    print('  SIN manual_columns configurado -> rows.py NO valida nada al editar en linea')
else:
    try:
        cols = json.loads(mc['valor'])
    except Exception:
        cols = []
    defs = [c for c in cols if str(c.get('nombre', '')).strip() == 'ESTADO COTIZACION']
    if not defs:
        print('  ESTADO COTIZACION no esta en manual_columns -> rows.py NO valida nada')
    for c in defs:
        print('  tipo=%r' % c.get('tipo'))
        for o in (c.get('opciones') or []):
            print('    opcion: %r' % o)

# ── 4. Historial: quien escribio ese estado y cuando ────────────────────────
print('\n=== HISTORIAL: cambios de ESTADO COTIZACION con "Pendiente" ===')
rows = cur.execute(
    "SELECT key_value, username, valor_anterior, valor_nuevo, fecha, campo_modificado "
    "FROM historial_cambios WHERE proyecto_id = ? AND campo_modificado LIKE '%ESTADO%' "
    "AND (valor_nuevo LIKE '%Pendiente%' OR valor_anterior LIKE '%Pendiente%') "
    "ORDER BY fecha", (pid,)
).fetchall()
if not rows:
    print('  Sin registros en historial.')
for r in rows:
    print('  %s | %s | %r -> %r | %s' % (
        r['key_value'], r['username'], r['valor_anterior'], r['valor_nuevo'], r['fecha']))

print('\n=== HISTORIAL: TODOS los valores nuevos distintos de ESTADO COTIZACION ===')
vals = cur.execute(
    "SELECT valor_nuevo, COUNT(*) n, MIN(fecha) desde, MAX(fecha) hasta, "
    "GROUP_CONCAT(DISTINCT username) quienes FROM historial_cambios "
    "WHERE proyecto_id = ? AND campo_modificado LIKE '%ESTADO COTIZACION%' "
    "GROUP BY valor_nuevo ORDER BY n DESC", (pid,)
).fetchall()
if not vals:
    print('  Sin registros en historial para ESTADO COTIZACION.')
for r in vals:
    print('  %-30r %4d  %s .. %s  por: %s' % (
        r['valor_nuevo'], r['n'], r['desde'], r['hasta'], r['quienes']))

con.close()
