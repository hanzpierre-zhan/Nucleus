"""Prueba de concurrencia; solo para una rama Neon aislada expresamente indicada."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db import db
from models import AppConfig, NucleusData, Proyecto
from services.cotizacion_numeracion import reservar, siguiente


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    url = config['database_url']
    if config.get('branch_id') != 'br-withered-darkness-axlnww9l':
        raise SystemExit('Solo se permite la rama aislada de verificación.')
    if 'ep-old-queen-ax41x5bx' in urlsplit(url).hostname:
        raise SystemExit('Producción bloqueada para esta prueba.')
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=url.replace('postgresql://', 'postgresql+psycopg2://', 1),
                      SQLALCHEMY_ENGINE_OPTIONS={'pool_size': 8, 'max_overflow': 0})
    db.init_app(app)
    with app.app_context():
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        fecha = datetime(2026, 10, 29)
        inicio = siguiente(pid, fecha.year)

    def alta(index):
        with app.app_context():
            prefijo = ('CL', 'EN', 'IN', 'PX')[index % 4]
            key, orden = reservar(pid, prefijo, fecha, 'PX-2026-10-000526')
            db.session.add(NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps({
                'N° COTIZACION': key, 'N° ORDEN': orden, 'CLIENTE': prefijo,
                '_PRUEBA_NUMERACION': True})))
            db.session.commit()
            return key, orden

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(alta, range(12)))
    assert len({key.rsplit('-', 1)[1] for key, _ in resultados}) == 12
    assert len({orden for _, orden in resultados}) == 12
    assert sorted(int(key.rsplit('-', 1)[1]) for key, _ in resultados) == list(range(inicio, inicio + 12))
    with app.app_context():
        assert siguiente(pid, fecha.year) == inicio + 12
        # También protege escrituras que se saltan el asignador de la aplicación.
        numero = resultados[0][0].split('-')[-1]
        repetido = f'HW-2026-11-{numero}'
        db.session.add(NucleusData(proyecto_id=pid, key_value=repetido, data_json=json.dumps({
            'N° COTIZACION': repetido, 'N° ORDEN': '9999999'})))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError('Se admitió un consecutivo repetido entre clientes/meses.')
        key, orden = reservar(pid, 'CL', fecha)
        db.session.add(NucleusData(proyecto_id=pid, key_value=key, data_json=json.dumps({
            'N° COTIZACION': key, 'N° ORDEN': resultados[0][1]})))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError('Se admitió una orden repetida.')
        assert siguiente(pid, fecha.year) == inicio + 12
        print(json.dumps({'altas_concurrentes': len(resultados), 'numero_inicial': inicio,
                          'numero_siguiente': inicio + 12, 'ordenes_unicas': True,
                          'duplicados_rechazados_por_postgres': True, 'rollback_correcto': True}))


if __name__ == '__main__':
    main()
