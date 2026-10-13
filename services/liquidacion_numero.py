from sqlalchemy.exc import IntegrityError
from db import db
from models import LiquidacionNumero


def numero_liquidacion(origen_id):
    numero = LiquidacionNumero.query.filter_by(origen_id=origen_id).first()
    if numero is None:
        try:
            with db.session.begin_nested():
                numero = LiquidacionNumero(origen_id=origen_id)
                db.session.add(numero)
                db.session.flush()
        except IntegrityError:
            numero = LiquidacionNumero.query.filter_by(origen_id=origen_id).one()
    return f'C-{numero.id:08d}'


def numerar_historicos():
    """Asignar los casos anteriores antes de recibir nuevas aprobaciones."""
    import json
    from models import Proyecto, NucleusData
    proyecto = Proyecto.query.filter_by(nombre='Cotizaciones').first()
    if proyecto is None:
        return
    existentes = {n.origen_id for n in LiquidacionNumero.query.all()}
    pendientes = (NucleusData.query.filter_by(proyecto_id=proyecto.id)
                  .order_by(NucleusData.id).all())
    cambio = False
    for fila in pendientes:
        if fila.id in existentes:
            continue
        try:
            datos = json.loads(fila.data_json)
        except (ValueError, TypeError):
            continue
        from blueprints.refacturable import _ingresada
        if _ingresada(datos):
            numero_liquidacion(fila.id)
            cambio = True
    if cambio:
        db.session.commit()
