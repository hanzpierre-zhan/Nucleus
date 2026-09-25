# cleanup_old_flm.py - Limpia referencias residuales de FLM (old) id=1 y lo elimina
from urllib.parse import urlparse
import psycopg2

URL = 'postgresql://neondb_owner:npg_K4mS2IGveEBw@ep-old-queen-ax41x5bx-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require'
p = urlparse(URL)
conn = psycopg2.connect(
    host=p.hostname, port=p.port or 5432,
    dbname=p.path.lstrip('/'),
    user=p.username, password=p.password,
    sslmode='require'
)
conn.autocommit = False
cur = conn.cursor()

OLD_ID = 1   # FLM (old)
NEW_ID = 14  # FLM - ENTEL

print("Verificando estado actual...")
for t in ['nucleus_data', 'app_config', 'historial_cambios', 'accesos_proyecto', 'cotizaciones']:
    cur.execute(f"SELECT COUNT(*) FROM {t} WHERE proyecto_id=%s", (OLD_ID,))
    cnt = cur.fetchone()[0]
    if cnt > 0:
        print(f"  {t}: {cnt} filas residuales con proyecto_id={OLD_ID}")

print("\nMoviendo residuos a FLM - ENTEL (id=14)...")

# nucleus_data residual
cur.execute("SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=%s", (OLD_ID,))
nd_cnt = cur.fetchone()[0]
if nd_cnt > 0:
    cur.execute("""
        UPDATE nucleus_data SET proyecto_id=%s
        WHERE proyecto_id=%s
        AND key_value NOT IN (SELECT key_value FROM nucleus_data WHERE proyecto_id=%s)
    """, (NEW_ID, OLD_ID, NEW_ID))
    moved = cur.rowcount
    print(f"  nucleus_data: {moved} filas movidas (nuevas)")
    # Borrar duplicados que no se pudieron mover
    cur.execute("DELETE FROM nucleus_data WHERE proyecto_id=%s", (OLD_ID,))
    deleted = cur.rowcount
    if deleted > 0:
        print(f"  nucleus_data: {deleted} duplicados eliminados")

# Limpiar todas las otras tablas con referencias a OLD_ID
for t in ['app_config', 'filtros_maestros', 'tablas_maestras', 'reglas_estado_manual',
          'kpi_configs', 'historial_cambios', 'tecnicos', 'nucleus_history',
          'accesos_proyecto', 'cotizaciones']:
    try:
        cur.execute(f"DELETE FROM {t} WHERE proyecto_id=%s", (OLD_ID,))
        if cur.rowcount > 0:
            print(f"  {t}: {cur.rowcount} residuos eliminados")
    except Exception as e:
        conn.rollback()
        print(f"  {t}: aviso - {e}")

# Ahora si eliminar el proyecto viejo
try:
    cur.execute("DELETE FROM proyectos WHERE id=%s", (OLD_ID,))
    conn.commit()
    print("\nOK - Proyecto FLM (old) id=1 eliminado definitivamente.")
except Exception as e:
    conn.rollback()
    print(f"\nERROR eliminando proyecto: {e}")

# Verificacion final
print("\n=== ESTADO FINAL EN NEON ===")
cur.execute("SELECT nombre, (SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=p.id) FROM proyectos p ORDER BY nombre")
for row in cur.fetchall():
    marker = " <-- OK" if row[0] == 'FLM - ENTEL' else ""
    print(f"  {row[0]}: {row[1]} registros{marker}")

cur.close()
conn.close()
