"""Instala la conciliación una sola vez, al publicar el editor compatible."""
from pathlib import Path

from db import db


def instalar():
    if db.engine.dialect.name != 'postgresql':
        return []
    sql = (Path(__file__).resolve().parents[1] / 'scripts/sql/cotizacion_correlativos_20261029.sql').read_text(encoding='utf-8')
    with db.engine.begin() as connection:
        with connection.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM proyectos WHERE nombre='Cotizaciones'")
            proyecto = cursor.fetchone()
            if proyecto is None:
                return []
            pid = proyecto[0]
            cursor.execute("SET LOCAL lock_timeout='10s'")
            # Mismo bloqueo que las altas y que los otros workers del despliegue.
            cursor.execute("SELECT 1 FROM app_config WHERE proyecto_id=%s AND clave='cotizacion_next_seq' FOR UPDATE", (pid,))
            cursor.execute("SELECT valor FROM app_config WHERE proyecto_id=%s AND clave='cotizacion_guardas_v2'", (pid,))
            if cursor.fetchone():
                return []
            cursor.execute(sql)
            cambios = cursor.fetchall()
            cursor.execute("INSERT INTO app_config(proyecto_id,clave,valor) VALUES(%s,'cotizacion_guardas_v2','aplicado-20261029')", (pid,))
            return cambios
