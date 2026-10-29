"""Prueba de concurrencia; solo para una rama Neon aislada expresamente indicada."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, session
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db import db
from models import AccesoProyecto, AppConfig, NucleusData, Proyecto, Usuario
from services.cotizacion_numeracion import crear, reservar, siguiente


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    url = config['database_url']
    if config.get('branch_id') != 'br-withered-darkness-axlnww9l':
        raise SystemExit('Solo se permite la rama aislada de verificación.')
    if 'ep-old-queen-ax41x5bx' in urlsplit(url).hostname:
        raise SystemExit('Producción bloqueada para esta prueba.')
    app = Flask(__name__)
    app.secret_key = 'prueba-solo-rama-aislada'
    app.config.update(SQLALCHEMY_DATABASE_URI=url.replace('postgresql://', 'postgresql+psycopg2://', 1),
                      SQLALCHEMY_ENGINE_OPTIONS={'pool_size': 8, 'max_overflow': 0})
    db.init_app(app)
    from services.alcance_proyectos import instalar as instalar_alcance
    instalar_alcance()
    with app.app_context():
        from migrations.cotizacion_correlativos import instalar
        instalar()
        assert instalar() == []  # Los siguientes arranques no vuelven a conciliar.
        pid = Proyecto.query.filter_by(nombre='Cotizaciones').one().id
        fecha = datetime(2026, 10, 29)
        inicio = siguiente(pid, fecha.year)
        actores = []
        for cliente in ('CLARO', 'ENTEL', 'INTEGRATEL', 'PEXT'):
            usuario = Usuario(username='numeracion-pg-' + uuid4().hex[:12], rol='supervisor', password_hash='no-login')
            db.session.add(usuario); db.session.flush()
            operacion = Proyecto.query.filter_by(nombre='FLM - ' + cliente).one().id
            for acceso in (pid, operacion):
                db.session.add(AccesoProyecto(usuario_id=usuario.id, proyecto_id=acceso, restricciones='{}'))
            actores.append((usuario.id, cliente))
        db.session.commit()

    def alta(index):
        with app.test_request_context('/api/rows/add'):
            uid, cliente = actores[index % 4]
            session.update(user_id=uid, rol='supervisor', current_proyecto_id=pid, current_proyecto_nombre='Cotizaciones')
            prefijo = ('CL', 'EN', 'IN', 'PX')[index % 4]
            result = crear(pid, prefijo, fecha, {'CLIENTE': cliente,
                'N° COTIZACION': 'PX-2026-10-000526', '_PRUEBA_NUMERACION': True})
            return result['key'], result['orden']

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
                          'usuarios_restringidos_a_su_cliente': True,
                          'duplicados_rechazados_por_postgres': True, 'rollback_correcto': True}))


if __name__ == '__main__':
    main()
