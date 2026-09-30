import sqlite3
import json

PERMITIDAS = {
    'Marca temporal',
    'Nombre del proyecto',
    'Tipo de presupuesto',
    'Tipo de gasto',
    'Documento del beneficiario',
    'Técnico beneficiario',
    'Nombre de site',
    'Número CM / PM / PLM',
    'Criticidad - Prioridad',
    'Motivo de la solicitud',
    'Monto total del depósito',
    'Tipo de depósito a realizar',
    'Número de celular o CCI',
    'Titular de la cuenta',
    'Responsable de la validación',
    'Observaciones (Form)'
}

# Columnas internas que NO deben borrarse si ya existen
SISTEMA = {
    'ESTADO', 'INTERACCION', 'FECHA VALIDACION', 'VALIDADO POR', 'OBSERVACIONES',
    'FECHA PAGO', 'MONTO PAGO', 'FOTO PAGO', 'DEPOSITADO POR', 'FOTOS SUSTENTO',
    'COMENTARIOS SUSTENTO', 'FECHA SUSTENTO', 'SUSTENTADO POR', 'FECHA RECHAZO', 'RECHAZADO POR',
    'EDITADO POR', '_fecha_ultima_act_manual', '_ultimo_usuario_manual'
}

def clean_db():
    db = sqlite3.connect('nucleus.db')
    c = db.cursor()
    c.execute("SELECT id FROM proyectos WHERE nombre = 'Rendicion'")
    p = c.fetchone()
    if not p:
        print("Rendicion not found")
        return
    proy_id = p[0]
    
    c.execute("SELECT id, data_json FROM nucleus_data WHERE proyecto_id = ?", (proy_id,))
    rows = c.fetchall()
    
    todas_columnas_encontradas = set()
    actualizados = 0
    for row_id, data_json in rows:
        try:
            data = json.loads(data_json)
        except:
            continue
        nuevo_data = {}
        for k, v in data.items():
            if k in PERMITIDAS or k in SISTEMA:
                nuevo_data[k] = v
        
        todas_columnas_encontradas.update(nuevo_data.keys())
        
        nuevo_json = json.dumps(nuevo_data, ensure_ascii=False)
        if nuevo_json != data_json:
            c.execute("UPDATE nucleus_data SET data_json = ? WHERE id = ?", (nuevo_json, row_id))
            actualizados += 1
            
    print(f"Filas actualizadas: {actualizados}")
    
    # Update app_schema
    schema_cols_filtradas = [col for col in todas_columnas_encontradas if col not in SISTEMA]
    
    c.execute("UPDATE app_config SET valor = ? WHERE clave = 'app_schema' AND proyecto_id = ?", 
              (json.dumps(sorted(schema_cols_filtradas), ensure_ascii=False), proy_id))
    
    db.commit()
    print("app_schema actualizado:", sorted(schema_cols_filtradas))
    db.close()

if __name__ == "__main__":
    clean_db()
