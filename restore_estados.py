"""
Restaura el campo ESTADO (y otros campos operacionales perdidos) 
en las filas de Rendicion que quedaron sin ESTADO tras el fix_all.py.
"""
import sqlite3, json, sys

FOTO_MAP = {
    # key_value -> foto_pago_url (extraídas del log de check_depositos.py)
    '29/9/2026 15:41:05': {'ESTADO': 'DEPOSITADO', 'FOTO PAGO': '/api/rendicion/foto/11/29_9_2026_154105/rendicion_pago.jpg?v=1790804126', 'FECHA PAGO': '2026-09-30', 'MONTO PAGO': '511.6', 'DEPOSITADO POR': 'hvargas'},
    '29/9/2026 15:42:33': {'ESTADO': 'DEPOSITADO', 'FOTO PAGO': '/api/rendicion/foto/11/29_9_2026_154233/rendicion_pago.jpg?v=1790799077', 'FECHA PAGO': '2026-09-30', 'MONTO PAGO': '536.94', 'DEPOSITADO POR': 'hvargas'},
    '29/9/2026 15:43:01': {'ESTADO': 'DEPOSITADO', 'FOTO PAGO': '/api/rendicion/foto/11/29_9_2026_154301/rendicion_pago.jpg?v=1790799487', 'FECHA PAGO': '2026-09-30', 'MONTO PAGO': '536.94', 'DEPOSITADO POR': 'hvargas'},
    '29/9/2026 15:44:33': {'ESTADO': 'DEPOSITADO', 'FOTO PAGO': '/api/rendicion/foto/11/29_9_2026_154433/rendicion_pago.jpg?v=1790801298', 'FECHA PAGO': '2026-09-30', 'MONTO PAGO': '536.94', 'DEPOSITADO POR': 'hvargas'},
    '29/9/2026 15:45:01': {'ESTADO': 'DEPOSITADO', 'CODIGO DEPOSITO': 'COB-00001', 'FOTO PAGO': '/api/rendicion/foto/11/29_9_2026_154501/rendicion_pago.jpg?v=1790804759', 'FECHA PAGO': '2026-09-30', 'MONTO PAGO': '536.94', 'DEPOSITADO POR': 'hvargas'},
    '29/9/2026 15:45:20': {'ESTADO': 'VALIDADO', 'INTERACCION': 'hvargas', 'FECHA VALIDACION': '2026-09-30 19:52:43'},
    # Los otros 2 los ponemos como PENDIENTE para que el usuario los procese de nuevo
    '29/9/2026 15:41:45': {'ESTADO': 'PENDIENTE'},
    '29/9/2026 15:42:13': {'ESTADO': 'PENDIENTE'},
}

db = sqlite3.connect('nucleus.db')
c = db.cursor()

c.execute("SELECT key_value, data_json FROM nucleus_data WHERE proyecto_id = (SELECT id FROM proyectos WHERE nombre = 'Rendicion')")
rows = c.fetchall()

fixed = 0
for kv, dj in rows:
    d = json.loads(dj)
    if 'ESTADO' not in d and kv in FOTO_MAP:
        patch = FOTO_MAP[kv]
        d.update(patch)
        c.execute("UPDATE nucleus_data SET data_json = ? WHERE key_value = ?",
                  (json.dumps(d, ensure_ascii=False), kv))
        print(f"Restored {kv} -> ESTADO={patch['ESTADO']}")
        fixed += 1

db.commit()
print(f"\nFixed {fixed} rows.")
