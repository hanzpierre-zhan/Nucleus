import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, render_template, session, jsonify, abort, request
from services.utilidades import login_required, get_menu_proyectos, puede_cotizaciones
from db import db
from models import Proyecto, NucleusData, RefacturableDetalle

bp = Blueprint('refacturable', __name__, url_prefix='/refacturable')


def _autorizar():
    if not puede_cotizaciones(session.get('user_id'), session.get('rol'), session.get('current_proyecto_nombre')):
        abort(403)


def _aprobada(datos):
    estado = str(datos.get('ESTADO COTIZACION') or '').strip().lower()
    return estado in ('aprobado', 'atendido', 'validado') or (
        bool(datos.get('FECHA APROBACION')) and estado not in ('cancelado', 'rechazado'))


def _ingresada(datos):
    return bool(datos.get('_LIQUIDACION_INGRESO')) or _aprobada(datos)



def _documentos(datos, obras):
    from blueprints.cotizacion import _split_wos, _leer_evidencia_wo
    wos=_split_wos(datos.get('NUMERO WO'))
    if wos and any(json.loads(obras[w.lower()][1].data_json or '{}').get('_COT_EVIDENCIA_MIGRADA') for w in wos if w.lower() in obras):
        datos={c:v for c,v in datos.items() if not c.startswith(('_EVIDENCIA_','_BITACORA_'))}
    fotos = {fase: [] for fase in ('inicio', 'proceso', 'cierre')}
    comentarios = {fase: str(datos.get('_BITACORA_' + fase.upper()) or '') for fase in fotos}
    for fase in fotos:
        valor = datos.get('_EVIDENCIA_' + fase.upper()) or []
        try:
            valor = json.loads(valor) if isinstance(valor, str) else valor
        except (ValueError, TypeError):
            valor = []
        fotos[fase] = [url for url in valor if isinstance(url, str)] if isinstance(valor, list) else []
    proyectos, estados = set(), []
    for wo in _split_wos(datos.get('NUMERO WO')):
        resultado = obras.get(str(wo).strip().lower())
        if not resultado:
            continue
        proyecto, fila = resultado
        for nombre in ('ENTEL', 'CLARO', 'INTEGRATEL'):
            if nombre in proyecto.nombre.upper():
                proyectos.add(nombre)
        try:
            origen = json.loads(fila.data_json or '{}')
        except (ValueError, TypeError):
            origen = {}
        estado = str(origen.get('ESTADO DE EJECUCION') or origen.get('ESTADO EJECUCION') or 'Pendiente').strip()
        estados.append(estado if estado in ESTATUS else 'Pendiente')
        f, b = _leer_evidencia_wo(fila)
        for fase in fotos:
            fotos[fase] = list(dict.fromkeys(fotos[fase] + f[fase]))
            if b[fase] and b[fase] not in comentarios[fase]:
                comentarios[fase] += ('\n' if comentarios[fase] else '') + b[fase]
    proyecto = ', '.join(sorted(proyectos)) or str(datos.get('CLIENTE') or datos.get('PROYECTO') or '').upper()
    estado = 'Pendiente' if not estados or 'Pendiente' in estados else ('Stand by' if 'Stand by' in estados else 'Culminado')
    return fotos, comentarios, proyecto, estado


def _url_documento(valor):
    url = str(valor or '').strip()
    return url if url.startswith('/api/cotizacion/correo/') else ''


def _registros():
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not proyecto:
        return []
    from blueprints.cotizacion import _PROYECTOS_WO_SUSTENTO
    obras = {}
    proyectos_obra = {p.id: p for p in Proyecto.query.filter(Proyecto.nombre.in_(_PROYECTOS_WO_SUSTENTO)).all()}
    if proyectos_obra:
        for fila in NucleusData.query.filter(NucleusData.proyecto_id.in_(proyectos_obra)).all():
            obras.setdefault(str(fila.key_value).strip().lower(), (proyectos_obra[fila.proyecto_id], fila))
    from models import LiquidacionNumero
    from services.liquidacion_numero import numero_liquidacion
    detalles = {d.origen_id: json.loads(d.data_json or '{}') for d in RefacturableDetalle.query.all()}
    numeros = {n.origen_id: f'C-{n.id:08d}' for n in LiquidacionNumero.query.all()}
    filas = NucleusData.query.filter_by(proyecto_id=proyecto.id).order_by(NucleusData.id).all()
    casos = []
    nuevos = False
    for registro in filas:
        try:
            datos = json.loads(registro.data_json)
        except (ValueError, TypeError):
            continue
        if _ingresada(datos):
            casos.append((registro, datos))
            if registro.id not in numeros:
                numeros[registro.id] = numero_liquidacion(registro.id)
                nuevos = True
    if nuevos: db.session.commit()
    registros = []
    for registro, datos in reversed(casos):
        if not _ingresada(datos):
            continue
        seguimiento = detalles.get(registro.id, {})
        from blueprints.cotizacion import _split_wos,_resolver_sustento_cot
        obras_registro=dict(obras)
        for wo in _split_wos(datos.get('NUMERO WO')):
            obras_registro[wo.lower()]=_resolver_sustento_cot(registro,wo,datos)
        trabajos=[json.loads(obras_registro[w.lower()][1].data_json or '{}') for w in _split_wos(datos.get('NUMERO WO'))]
        inicios=[str(w.get('INICIO EJECUCION'))[:10] for w in trabajos if w.get('INICIO EJECUCION')]
        finales=[str(w.get('FIN EJECUCION'))[:10] for w in trabajos if w.get('FIN EJECUCION')]
        monto_hw = _monto(datos.get('SUB TOTAL + FEE'))
        monto_cobra = _monto(seguimiento.get('monto_cobra'))
        margen = monto_cobra - monto_hw if monto_cobra is not None and monto_hw is not None else None
        fotos, comentarios, nombre_proyecto, ejecucion = _documentos(datos, obras_registro)
        respaldo = {
            'sustento': any(fotos.values()) and (bool(datos.get('_SUSTENTO_VALIDADO')) or str(datos.get('ESTADO COTIZACION') or '').lower() == 'atendido'),
            'factura': bool(_url_documento(datos.get('ADJUNTO FACTURA PROVEEDOR'))),
            'correo': bool(_url_documento(datos.get('ADJUNTO CORREO CLIENTE'))),
            'cotizacion': str(datos.get('GENERADA') or '') == '1',
        }
        documentos = {nombre: ('No aplica' if seguimiento.get('no_aplica_' + nombre) == '1' else ('Completo' if completo else 'Pendiente')) for nombre, completo in respaldo.items()}
        aplicables = [estado for estado in documentos.values() if estado != 'No aplica']
        avance = round(100 * sum(estado == 'Completo' for estado in aplicables) / len(aplicables)) if aplicables else 100
        registros.append({
            **seguimiento,
            'id': registro.id,
            'cotizacion': datos.get('N° COTIZACION') or registro.key_value,
            'estado_cotizacion': datos.get('ESTADO COTIZACION') or '',
            'tipo_gasto': datos.get('TIPO GASTO APROBACION') or '',
            'gestor': datos.get('SOLICITADO POR') or datos.get('GESTOR') or '',
            'correlativo': numeros[registro.id],
            'fecha_inicio': min(inicios) if inicios else (datos.get('FECHA INICIO OBRA') or ''),
            'fecha_fin': max(finales) if finales else (datos.get('FECHA FIN OBRA') or ''),
            'estatus': ejecucion,
            'nombre_proyecto': nombre_proyecto,
            'factura_proveedor': _url_documento(datos.get('ADJUNTO FACTURA PROVEEDOR')),
            'correo_cliente': _url_documento(datos.get('ADJUNTO CORREO CLIENTE')),
            'cotizacion_generada': respaldo['cotizacion'],
            'documentos': documentos,
            'avance': avance,
            'fotos': fotos,
            'comentarios': comentarios,
            'monto_factura_proveedor': _importe(_monto(datos.get('SUBTOTAL FACTURA PROVEEDOR'))),
            'estado_liquidacion': seguimiento.get('estado_liquidacion') or seguimiento.get('estado_expense') or 'Pendiente',
            'numero_wo': datos.get('NUMERO WO') or '',
            'monto_hw': _importe(monto_hw),
            'monto_cobra': _importe(monto_cobra),
            'margen': _importe(margen),
        })
    return registros


@bp.route('/')
@login_required
def index():
    _autorizar()
    proyectos_list = get_menu_proyectos(session.get('user_id'), session.get('rol'))
    return render_template('refacturable.html', proyectos_list=proyectos_list)


@bp.route('/api/registros')
@login_required
def registros():
    _autorizar()
    return jsonify({'registros': _registros()})


CAMPOS_MANUALES = {
    'monto_cobra', 'numero_expense',
    'estado_expense', 'observacion', 'mes_cierre', 'numero_po', 'codigo_ajb_ejb', 'estado_liquidacion',
    'no_aplica_sustento', 'no_aplica_factura', 'no_aplica_correo', 'no_aplica_cotizacion',
}
ESTATUS = ('Pendiente', 'Stand by', 'Culminado')
ESTADOS_EXPENSE = ('En borrador', 'En revisión', 'Observado', 'Rechazado', 'Aprobado', 'Pendiente', 'Con PO')


def _monto(valor):
    if valor is None or str(valor).strip() == '':
        return None
    texto = re.sub(r'^(S/\.?|PEN)\s*', '', str(valor).strip(), flags=re.I).replace(' ', '')
    if ',' in texto and '.' in texto:
        texto = texto.replace(',', '') if texto.rfind('.') > texto.rfind(',') else texto.replace('.', '').replace(',', '.')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        importe = Decimal(texto)
        if not importe.is_finite() or abs(importe) > Decimal('999999999999'):
            return None
        return importe.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _importe(valor):
    return format(valor, '.2f') if valor is not None else ''


@bp.route('/api/registros/<int:origen_id>', methods=['PATCH'])
@login_required
def guardar(origen_id):
    _autorizar()
    origen = db.session.get(NucleusData, origen_id)
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not origen or not proyecto or origen.proyecto_id != proyecto.id:
        return jsonify({'error': 'Cotización no encontrada.'}), 404
    if not _ingresada(json.loads(origen.data_json)):
        return jsonify({'error': 'La cotización debe estar aprobada.'}), 409
    cambios = request.get_json(silent=True)
    if not isinstance(cambios, dict) or not cambios or set(cambios) - CAMPOS_MANUALES:
        return jsonify({'error': 'Solo puedes editar los campos manuales de Liquidaciones.'}), 400
    nuevos = {}
    for campo, valor in cambios.items():
        if not isinstance(valor, (str, int, float)) and valor is not None:
            return jsonify({'error': 'Valor de campo inválido.'}), 400
        valor = str(valor if valor is not None else '').strip()
        if len(valor) > (4000 if campo == 'observacion' else 200):
            return jsonify({'error': 'El texto supera el tamaño permitido.'}), 400
        if campo == 'monto_cobra' and valor:
            numero = _monto(valor)
            if numero is None or numero < 0:
                return jsonify({'error': 'Monto Cobra debe ser un importe válido mayor o igual a cero.'}), 400
            valor = _importe(numero)
        if campo == 'estatus' and valor and valor not in ESTATUS:
            return jsonify({'error': 'Estatus inválido.'}), 400
        if campo in ('estado_expense', 'estado_liquidacion') and valor and valor not in ESTADOS_EXPENSE:
            return jsonify({'error': 'Estado Expense inválido.'}), 400
        if campo in ('fecha_fin', 'mes_cierre') and valor:
            formato = '%Y-%m-%d' if campo == 'fecha_fin' else '%Y-%m'
            try:
                datetime.strptime(valor, formato)
            except ValueError:
                return jsonify({'error': 'Fecha inválida.'}), 400
        if campo.startswith('no_aplica_') and valor not in ('', '0', '1'):
            return jsonify({'error': 'La opción No aplica es inválida.'}), 400
        nuevos[campo] = valor
    detalle = db.session.get(RefacturableDetalle, origen_id)
    if not detalle:
        detalle = RefacturableDetalle(origen_id=origen_id)
        db.session.add(detalle)
    seguimiento = json.loads(detalle.data_json or '{}')
    seguimiento.update(nuevos)
    detalle.data_json = json.dumps(seguimiento, ensure_ascii=False)
    detalle.actualizado_por = str(session.get('username') or session.get('user_id') or '')
    detalle.actualizado_en = datetime.utcnow()
    db.session.commit()
    return jsonify({'registro': next(r for r in _registros() if r['id'] == origen_id)})

@bp.route('/api/registros/<int:origen_id>/pdf')
@login_required
def descargar_pdf(origen_id):
    _autorizar()
    origen = db.session.get(NucleusData, origen_id)
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not origen or not proyecto or origen.proyecto_id != proyecto.id:
        abort(404)
    datos = json.loads(origen.data_json or '{}')
    if not _ingresada(datos) or str(datos.get('GENERADA') or '') != '1':
        abort(409)
    from blueprints.cotizacion import _cotizacion_registro_pdf_response
    return _cotizacion_registro_pdf_response(origen)

@bp.route('/api/registros/<int:origen_id>/expediente')
@login_required
def descargar_expediente(origen_id):
    """Expediente de los respaldos vinculados, sin consultar URLs externas."""
    import os
    import tempfile
    import zipfile
    from urllib.parse import urlsplit, unquote
    from flask import send_file, current_app
    from werkzeug.utils import secure_filename
    from services.apoyo import evidencia_folder, evidencia_usa_b2, b2_cliente
    from blueprints.cotizacion import _cot_folder, _cotizacion_registro_pdf_response

    _autorizar()
    origen = db.session.get(NucleusData, origen_id)
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not origen or not proyecto or origen.proyecto_id != proyecto.id:
        abort(404)
    datos = json.loads(origen.data_json or '{}')
    if not _ingresada(datos):
        abort(409)
    row = next((r for r in _registros() if r['id'] == origen_id), None)
    if not row:
        abort(404)
    numero = secure_filename(row['correlativo'])
    archivo = tempfile.TemporaryFile()
    resumen = [f"Expediente: {numero}", f"Cotización: {row['cotizacion']}",
               f"WO: {row['numero_wo']}", f"Inicio: {row['fecha_inicio']}", f"Fin: {row['fecha_fin']}"]
    total = 0

    def adjuntar(zf, url, destino, tipo):
        nonlocal total
        partes = urlsplit(str(url or ''))
        ruta = unquote(partes.path)
        patron = r'/api/(evidencia/foto|cotizacion/correo)/(\d+)/([^/]+)/([^/]+)'
        match = re.fullmatch(patron, ruta)
        if partes.scheme or partes.netloc or not match or match[1] != tipo:
            raise ValueError('Referencia no válida')
        pid, key, nombre = int(match[2]), match[3], match[4]
        if any(x in key or x in nombre for x in ('..', '\\', '\x00')):
            raise ValueError('Referencia no válida')
        if tipo == 'cotizacion/correo' and pid != proyecto.id:
            raise ValueError('Proyecto no válido')
        if evidencia_usa_b2():
            fuente = b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'], Key=f'{key}/{nombre}')['Body']
        else:
            folder = evidencia_folder(pid, key) if tipo == 'evidencia/foto' else _cot_folder(pid, key)
            fuente = open(os.path.join(folder, nombre), 'rb')
        try:
            # Copiar por bloques a disco; limitar el expediente a 250 MiB.
            with zf.open(f'{numero}/{destino}/{secure_filename(nombre) or "adjunto"}', 'w') as salida:
                while True:
                    bloque = fuente.read(65536)
                    if not bloque:
                        break
                    total += len(bloque)
                    if total > 250 * 1024 * 1024:
                        raise OverflowError('El expediente supera 250 MiB')
                    salida.write(bloque)
        finally:
            fuente.close()

    try:
        with zipfile.ZipFile(archivo, 'w', zipfile.ZIP_DEFLATED) as zf:
            for kind, estado in row['documentos'].items():
                resumen.append(f'{kind}: {estado}')
            for fase in ('inicio', 'proceso', 'cierre'):
                resumen.append(f"Comentario {fase}: {row['comentarios'].get(fase) or 'Sin comentarios'}")
                for indice, url in enumerate(row['fotos'].get(fase, []), 1):
                    try:
                        adjuntar(zf, url, f'01_Sustento_de_obra/{fase}/{indice:03d}', 'evidencia/foto')
                    except (OSError, ValueError, KeyError):
                        resumen.append(f'No disponible: foto {fase} {indice}')
                    except OverflowError:
                        raise
                    except Exception:
                        resumen.append(f'No disponible: foto {fase} {indice}')
            for kind, campo, carpeta in [('factura', 'factura_proveedor', '02_Factura_del_proveedor'),
                                         ('correo', 'correo_cliente', '03_Correo_del_cliente')]:
                if row.get(campo):
                    try:
                        adjuntar(zf, row[campo], carpeta, 'cotizacion/correo')
                    except OverflowError:
                        raise
                    except Exception:
                        resumen.append(f'No disponible: {kind}')
            if str(datos.get('GENERADA') or '') == '1':
                pdf = _cotizacion_registro_pdf_response(origen)
                if pdf.status_code != 200:
                    raise ValueError('No se pudo generar la cotización')
                zf.writestr(f'{numero}/04_Cotizacion_generada/{secure_filename(row["cotizacion"]) or "cotizacion"}.pdf', pdf.get_data())
            zf.writestr(f'{numero}/00_Resumen.txt', '\n'.join(resumen).encode('utf-8'))
        archivo.seek(0)
        return send_file(archivo, mimetype='application/zip', as_attachment=True,
                         download_name=f'{numero}.zip', max_age=0)
    except OverflowError:
        archivo.close()
        return jsonify({'error': 'El expediente supera 250 MiB. Descarga los respaldos individualmente.'}), 413
    except Exception:
        archivo.close()
        current_app.logger.exception('No se pudo preparar el expediente %s', origen_id)
        return jsonify({'error': 'No se pudo preparar el expediente. Intenta nuevamente.'}), 500
