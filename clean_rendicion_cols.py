import sqlite3
import json

# Columnas internas del módulo: nunca se borran de los datos.
# (CODIGO DEPOSITO lo escribe el flujo de depósito, no el form.)
SISTEMA = {
    'ESTADO', 'INTERACCION', 'CODIGO DEPOSITO', 'FECHA VALIDACION', 'VALIDADO POR',
    'OBSERVACIONES', 'FECHA PAGO', 'MONTO PAGO', 'FOTO PAGO', 'DEPOSITADO POR',
    'FOTOS SUSTENTO', 'COMENTARIOS SUSTENTO', 'FECHA SUSTENTO', 'SUSTENTADO POR',
    'FECHA RECHAZO', 'RECHAZADO POR', 'EDITADO POR',
    '_fecha_ultima_act_manual', '_ultimo_usuario_manual'
}

def clean_db():
    """Limpia claves basura de los data_json de Rendicion.

    IMPORTANTE: el esquema (app_schema) es DINÁMICO y lo define el CSV del
    Google Form en cada sync (/api/rendicion/sync). Este script NO debe
    reconstruir app_schema desde los datos: eso resucitaría columnas dadas de
    baja en el form. Solo se usa como lista blanca para depurar claves viejas.
    """
    db = sqlite3.connect('nucleus.db')
    c = db.cursor()
    c.execute("SELECT id FROM proyectos WHERE nombre = 'Rendicion'")
    p = c.fetchone()
    if not p:
        print("Rendicion not found")
        return
    proy_id = p[0]

    # Permitidas = columnas ACTUALES del esquema dinámico (form + hoja 2) + sistema.
    c.execute("SELECT valor FROM app_config WHERE clave = 'app_schema' AND proyecto_id = ?", (proy_id,))
    sc = c.fetchone()
    try:
        permitidas = set(json.loads(sc[0])) if sc and sc[0] else set()
    except Exception:
        permitidas = set()
    if not permitidas:
        print("app_schema vacio: corre antes /api/rendicion/sync")
        return
    permitidas |= SISTEMA

    c.execute("SELECT id, data_json FROM nucleus_data WHERE proyecto_id = ?", (proy_id,))
    rows = c.fetchall()

    actualizados = 0
    for row_id, data_json in rows:
        try:
            data = json.loads(data_json)
        except:
            continue
        nuevo_data = {k: v for k, v in data.items() if k in permitidas}

        nuevo_json = json.dumps(nuevo_data, ensure_ascii=False)
        if nuevo_json != data_json:
            c.execute("UPDATE nucleus_data SET data_json = ? WHERE id = ?", (nuevo_json, row_id))
            actualizados += 1

    print(f"Filas actualizadas: {actualizados}")
    print("app_schema intacto (dinámico, definido por el form):", sorted(permitidas - SISTEMA))
    db.commit()
    db.close()

if __name__ == "__main__":
    clean_db()
