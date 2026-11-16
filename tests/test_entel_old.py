import json

from db import db
from models import NucleusData, Proyecto


def test_cotizacion_encuentra_wo_en_backup_entel(app):
    with app.app_context():
        from blueprints.cotizacion import _resolver_wo_sustento
        from services.entel_old import NOMBRE, carpeta_de_fotos, proyectos_de_fotos
        entel = Proyecto.query.filter_by(nombre='FLM - ENTEL').one()
        backup = Proyecto(nombre=NOMBRE, descripcion='prueba')
        db.session.add(backup)
        db.session.flush()
        db.session.add(NucleusData(proyecto_id=backup.id, key_value='CM-QA-OLD-1', data_json=json.dumps({'BITACORA': 'x'})))
        db.session.commit()
        try:
            assert _resolver_wo_sustento('CM-QA-OLD-1', 'ENTEL')[0].id == backup.id
            assert _resolver_wo_sustento('CM-QA-OLD-1', 'CLARO') is None
            assert proyectos_de_fotos(entel.id) == {entel.id, backup.id}
            assert carpeta_de_fotos(backup.id) == entel.id
            # Si el WO vuelve a importarse en FLM - ENTEL, se usa ese y no el backup.
            db.session.add(NucleusData(proyecto_id=entel.id, key_value='CM-QA-OLD-1', data_json='{}'))
            db.session.commit()
            assert _resolver_wo_sustento('CM-QA-OLD-1', 'ENTEL')[0].id == entel.id
        finally:
            NucleusData.query.filter_by(key_value='CM-QA-OLD-1').delete()
            db.session.delete(backup)
            db.session.commit()
