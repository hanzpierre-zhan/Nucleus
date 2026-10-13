from db import db
from models import LiquidacionNumero
from services.liquidacion_numero import numero_liquidacion


def test_numero_permanente_y_no_reutilizado(app):
    with app.app_context():
        a=numero_liquidacion(900001);db.session.commit()
        assert numero_liquidacion(900001)==a
        b=numero_liquidacion(900002);db.session.commit()
        assert int(b[2:])==int(a[2:])+1
        LiquidacionNumero.query.filter_by(origen_id=900001).delete();db.session.commit()
        c=numero_liquidacion(900003);db.session.commit()
        assert int(c[2:])>int(b[2:])
        assert a.startswith('C-') and len(a)==10
