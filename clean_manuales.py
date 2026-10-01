import sqlite3
import json

def update_db():
    db = sqlite3.connect('nucleus.db')
    c = db.cursor()
    c.execute("SELECT id FROM proyectos WHERE nombre = 'Rendicion'")
    p = c.fetchone()
    if not p:
        print("Rendicion not found")
        return
    proy_id = p[0]
    
    # 1. Update manual_columns to ONLY keep ESTADO (or nothing)
    c.execute("SELECT valor FROM app_config WHERE clave = 'manual_columns' AND proyecto_id = ?", (proy_id,))
    s = c.fetchone()
    if s:
        manual_cols = json.loads(s[0])
        # Filtramos
        nuevas_manuales = [col for col in manual_cols if col.get('nombre') == 'ESTADO']
        c.execute("UPDATE app_config SET valor = ? WHERE clave = 'manual_columns' AND proyecto_id = ?", 
                  (json.dumps(nuevas_manuales, ensure_ascii=False), proy_id))
        print("manual_columns actualizadas:", nuevas_manuales)
        
    # 2. Delete column_layout to reset the UI state
    c.execute("DELETE FROM app_config WHERE clave = 'column_layout' AND proyecto_id = ?", (proy_id,))
    
    db.commit()
    db.close()
    print("Limpieza completada.")

if __name__ == "__main__":
    update_db()
