# -*- coding: utf-8 -*-
"""Patch to add migration route"""

import sys

content = """
@bp.route('/api/cotizacion/migrar_antiguos', methods=['POST'])
@login_required
def api_cotizacion_migrar_antiguos():
    \"\"\"Solo Zeno/Suport: Migra los registros antiguos (Ej: En proceso) a 'En Aprobación' (2. Cliente).\"\"\"
    if session.get('rol') not in ('zeno', 'suport'):
        return jsonify({'error': 'Solo administradores pueden migrar datos.'}), 403
    proy = _cot_proyecto()
    if not proy:
        return jsonify({'error': 'No existe el proyecto Cotizaciones.'}), 404
        
    try:
        recs = NucleusData.query.filter_by(proyecto_id=proy.id).all()
        count = 0
        for rec in recs:
            try:
                d = json.loads(rec.data_json)
                est = str(d.get('ESTADO COTIZACION', '') or '').strip()
                est_b = est.lower()
                
                # Excluir los estados que YA están mapeados a otras pestañas correctamente:
                # Pdt. Cotización (1), Atendido/Validado (3), Cancelado/Anulado (4), y los que ya están en 2.
                if est_b not in ('pdt. cotización', 'pdt. cotizacion', 'atendido', 'validado', 
                               'cancelado', 'anulado', 'en aprobación', 'en aprobacion', 'cotizado'):
                    d['ESTADO COTIZACION'] = 'En Aprobación'
                    rec.data_json = json.dumps(d, ensure_ascii=False)
                    count += 1
            except Exception:
                continue
        db.session.commit()
        return jsonify({'success': True, 'migrados': count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
"""

path = r'c:\Mega\Proyect\Nucleus\blueprints\cotizacion.py'
with open(path, 'r', encoding='utf-8') as f:
    orig = f.read()

if 'api_cotizacion_migrar_antiguos' not in orig:
    with open(path, 'a', encoding='utf-8') as f:
        f.write(content)
    print("Route appended OK")
else:
    print("Route already exists")
