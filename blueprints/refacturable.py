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


def _registros():
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if not proyecto:
        return []
    detalles = {d.origen_id: json.loads(d.data_json or '{}') for d in RefacturableDetalle.query.all()}
    registros = []
    for registro in NucleusData.query.filter_by(proyecto_id=proyecto.id).order_by(NucleusData.id.desc()).all():
        try:
            datos = json.loads(registro.data_json)
        except (ValueError, TypeError):
            continue
        if not _aprobada(datos):
            continue
        seguimiento = detalles.get(registro.id, {})
        monto_hw = _monto(datos.get('SUB TOTAL + FEE'))
        monto_cobra = _monto(seguimiento.get('monto_cobra'))
        margen = monto_cobra - monto_hw if monto_cobra is not None and monto_hw is not None else None
        registros.append({
            **seguimiento,
            'id': registro.id,
            'cotizacion': datos.get('N° COTIZACION') or registro.key_value,
            'estado_cotizacion': datos.get('ESTADO COTIZACION') or '',
            'gestor': datos.get('GESTOR') or '',
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
    'monto_cobra', 'fecha_fin', 'estatus', 'numero_expense',
    'estado_expense', 'observacion', 'mes_cierre', 'numero_po',
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
    if not _aprobada(json.loads(origen.data_json)):
        return jsonify({'error': 'La cotización debe estar aprobada.'}), 409
    cambios = request.get_json(silent=True)
    if not isinstance(cambios, dict) or not cambios or set(cambios) - CAMPOS_MANUALES:
        return jsonify({'error': 'Solo puedes editar los campos manuales de Refacturable.'}), 400
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
        if campo == 'estado_expense' and valor and valor not in ESTADOS_EXPENSE:
            return jsonify({'error': 'Estado Expense inválido.'}), 400
        if campo in ('fecha_fin', 'mes_cierre') and valor:
            formato = '%Y-%m-%d' if campo == 'fecha_fin' else '%Y-%m'
            try:
                datetime.strptime(valor, formato)
            except ValueError:
                return jsonify({'error': 'Fecha inválida.'}), 400
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
