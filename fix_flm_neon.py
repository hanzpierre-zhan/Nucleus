# fix_flm_neon.py - Fusiona "FLM (old)" -> "FLM - ENTEL" en Neon
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

cur.execute("SELECT id FROM proyectos WHERE nombre='FLM (old)'")
r = cur.fetchone()
old_id = r[0] if r else None

cur.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
r = cur.fetchone()
new_id = r[0] if r else None

print(f"FLM (old) id={old_id} | FLM - ENTEL id={new_id}")

if old_id and new_id:
    # Mover app_config con merge (evitar duplicados)
    try:
        cur.execute("SELECT clave, valor FROM app_config WHERE proyecto_id=%s", (old_id,))
        cfgs = cur.fetchall()
        for clave, valor in cfgs:
            cur.execute(
                """INSERT INTO app_config (proyecto_id, clave, valor)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (proyecto_id, clave) DO UPDATE SET valor=EXCLUDED.valor""",
                (new_id, clave, valor)
            )
        cur.execute("DELETE FROM app_config WHERE proyecto_id=%s", (old_id,))
        print(f"  app_config: {len(cfgs)} configs fusionadas")
    except Exception as e:
        conn.rollback()
        print(f"  app_config ERROR: {e}")

    tables = [
        'filtros_maestros', 'tablas_maestras', 'reglas_estado_manual',
        'kpi_configs', 'historial_cambios', 'tecnicos',
        'nucleus_history', 'accesos_proyecto', 'cotizaciones'
    ]
    for t in tables:
        try:
            cur.execute(f"UPDATE {t} SET proyecto_id=%s WHERE proyecto_id=%s", (new_id, old_id))
            print(f"  {t}: {cur.rowcount} filas movidas")
        except Exception as e:
            conn.rollback()
            print(f"  {t}: aviso - {e}")

    cur.execute("DELETE FROM proyectos WHERE id=%s", (old_id,))
    conn.commit()
    print("\nOK - FLM (old) fusionado en FLM - ENTEL y eliminado.")

elif old_id and not new_id:
    cur.execute("UPDATE proyectos SET nombre='FLM - ENTEL' WHERE id=%s", (old_id,))
    conn.commit()
    print("OK - FLM (old) renombrado directamente a FLM - ENTEL.")
else:
    print("No se encontro FLM (old) — nada que hacer.")

# Verificacion final
cur.execute("SELECT id FROM proyectos WHERE nombre='FLM - ENTEL'")
r = cur.fetchone()
if r:
    cur.execute("SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=%s", (r[0],))
    cnt = cur.fetchone()[0]
    print(f"\nFLM - ENTEL ahora tiene: {cnt} registros en Neon")
else:
    print("FLM - ENTEL no encontrado despues de la operacion")

cur.close()
conn.close()
