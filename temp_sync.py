
@bp.route('/api/rendicion/sync_sustentos', methods=['POST'])
def api_rendicion_sync_sustentos():
    """Sincroniza los sustentos desde la segunda hoja de Google Sheets."""
    rol = session.get('rol')
    autorizado = bool(session.get('user_id') and rol in ('admin', 'zeno', 'suport'))
    if not autorizado:
        return jsonify({'error': 'No autorizado.'}), 403

    proy = Proyecto.query.filter_by(nombre='Rendicion').first()
    if not proy:
        return jsonify({'error': 'Módulo Rendicion no existe.'}), 404

    csv_url = 'https://docs.google.com/spreadsheets/d/18CYUhXGN8jWk4hzr194p3vhdU6H90WD-O0Aw77WxgEY/export?format=csv&gid=831408062'
    try:
        req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as e:
        return jsonify({'error': 'No se pudo descargar el CSV de Sustentos: %s' % e}), 502
    
    text = raw.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []

    # Buscamos la columna CODIGO DEPOSITO
    col_codigo = next((f for f in fields if 'codigo' in str(f).lower() and 'deposito' in str(f).lower()), None)
    if not col_codigo:
        # Fallback a la primera columna o un nombre estandar
        col_codigo = 'CODIGO DEPOSITO' if 'CODIGO DEPOSITO' in fields else (fields[0] if fields else None)
    
    if not col_codigo:
         return jsonify({'error': 'No se encontro la columna CODIGO DEPOSITO en la hoja.'}), 400

    actualizados = 0
    omitidos = 0
    no_encontrados = 0
    t0 = time.time()
    
    for row in reader:
        cod = (row.get(col_codigo) or '').strip()
        if not cod: continue
        
        # Buscar en DB por CODIGO DEPOSITO
        all_data = NucleusData.query.filter_by(proyecto_id=proy.id).all()
        target = None
        target_dict = None
        for d in all_data:
            try:
                dj = json.loads(d.data_json)
                if str(dj.get('CODIGO DEPOSITO', '')).strip() == cod:
                    target = d
                    target_dict = dj
                    break
            except:
                pass
        
        if not target:
            no_encontrados += 1
            continue
            
        estado_actual = str(target_dict.get('ESTADO', '')).strip().upper()
        if estado_actual == 'DEPOSITADO':
            # Actualizamos estado y agregamos data
            for k, v in row.items():
                if k and k != col_codigo:
                    target_dict[f'SUSTENTO_{k.upper()}'] = str(v).strip()
            
            target_dict['ESTADO'] = 'CON SUSTENTO'
            target.data_json = safe_json_dumps(target_dict)
            actualizados += 1
        else:
            omitidos += 1
            
    db.session.commit()
    
    return jsonify({
        'success': True,
        'actualizados': actualizados,
        'omitidos_por_estado': omitidos,
        'no_encontrados': no_encontrados,
        'segundos': round(time.time() - t0, 2)
    })
