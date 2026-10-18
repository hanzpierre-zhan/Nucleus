# -*- coding: utf-8 -*-
"""El ZIP de respaldo debe tener EXACTAMENTE el mismo contenido JSON que antes
(acumular toda la tabla + json.dumps + writestr)."""
import io
import json
import os
import sys
import zipfile
from datetime import datetime

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

from app import create_app  # noqa: E402
from db import db  # noqa: E402
from models import (Usuario, Proyecto, AppConfig, NucleusData, NucleusHistory,  # noqa: E402
                    FiltroMaestro, TablaMaestra, ReglaEstadoManual, AccesoProyecto,
                    KpiConfig, HistorialCambios, Tecnico, Cotizacion)

MODELOS = {
    'usuarios': Usuario, 'proyectos': Proyecto, 'app_config': AppConfig,
    'nucleus_data': NucleusData, 'nucleus_history': NucleusHistory,
    'filtros_maestros': FiltroMaestro, 'tablas_maestras': TablaMaestra,
    'reglas_estado_manual': ReglaEstadoManual,
    'accesos_proyecto': AccesoProyecto, 'kpi_configs': KpiConfig,
    'historial_cambios': HistorialCambios, 'tecnicos': Tecnico,
    'cotizaciones': Cotizacion,
}


def referencia():
    """Copia literal del algoritmo anterior, en memoria."""
    contenido = {}
    for nombre, modelo in MODELOS.items():
        tiene_pid = hasattr(modelo, 'proyecto_id')
        if tiene_pid:
            pids = [r[0] for r in db.session.query(modelo.proyecto_id).distinct().all()]
            for _pid in pids:
                fil = []
                q = modelo.query.filter_by(proyecto_id=_pid).order_by(modelo.id)
                offset = 0
                while True:
                    lote = q.offset(offset).limit(2000).all()
                    if not lote:
                        break
                    for obj in lote:
                        d = {}
                        for col in modelo.__table__.columns:
                            v = getattr(obj, col.name)
                            if isinstance(v, datetime):
                                v = v.strftime('%Y-%m-%d %H:%M:%S')
                            d[col.name] = v
                        fil.append(d)
                    offset += len(lote)
                contenido[f'{nombre}_p{_pid}.json'] = json.dumps(fil, ensure_ascii=False)
        else:
            fil = []
            for obj in modelo.query.order_by(modelo.id).all():
                d = {}
                for col in modelo.__table__.columns:
                    v = getattr(obj, col.name)
                    if isinstance(v, datetime):
                        v = v.strftime('%Y-%m-%d %H:%M:%S')
                    d[col.name] = v
                fil.append(d)
            contenido[f'{nombre}.json'] = json.dumps(fil, ensure_ascii=False)
    return contenido


app = create_app()
c = app.test_client()
with c.session_transaction() as s:
    s['user_id'] = 2
    s['username'] = 'hvargas'
    s['rol'] = 'zeno'
    s['current_proyecto_id'] = 14
    s['current_proyecto_nombre'] = 'FLM - ENTEL'
r = c.get('/api/admin/export_zip')
assert r.status_code == 200, r.data[:200]

with app.app_context():
    ref = referencia()

with zipfile.ZipFile(io.BytesIO(r.data)) as zf:
    actuales = {n: zf.read(n) for n in zf.namelist() if n != 'manifest.json'}

print(f'entradas: nuevas={len(actuales)} referencia={len(ref)}')
faltan = set(ref) - set(actuales)
sobran = set(actuales) - set(ref)
print('faltan:', sorted(faltan)[:5], '| sobran:', sorted(sobran)[:5])
dif = [n for n in ref if n in actuales and actuales[n] != ref[n].encode('utf-8')]
print(f'archivos con bytes distintos: {len(dif)} {dif[:5]}')
print('CONTENIDO IDÉNTICO' if not faltan and not sobran and not dif else 'HAY DIFERENCIAS')
