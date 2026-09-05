"""Carga un respaldo (ZIP descargado de /api/admin/export_zip de producción)
en la DB LOCAL (sqlite nucleus.db) para probar sin tocar el dato original.

USO:
  python scripts/importar_respaldo.py C:/ruta/respaldo_nucleus_2026xxxx_xxxxxx.zip

ADVERTENCIA: borra el contenido actual de las tablas locales y lo reemplaza
por el del respaldo. No toca producción.
"""
import os
import sys
import json
import zipfile
from datetime import datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE)
# Forzar la DB local aunque haya un DATABASE_URL en el entorno
os.environ.pop('DATABASE_URL', None)

import app as A  # noqa: E402

ORDEN = ['usuarios', 'proyectos', 'app_config', 'nucleus_data', 'nucleus_history',
         'filtros_maestros', 'tablas_maestras', 'reglas_estado_manual',
         'accesos_proyecto', 'kpi_configs', 'historial_cambios', 'tecnicos',
         'cotizaciones']
MODELOS = {
    'usuarios': A.Usuario, 'proyectos': A.Proyecto, 'app_config': A.AppConfig,
    'nucleus_data': A.NucleusData, 'nucleus_history': A.NucleusHistory,
    'filtros_maestros': A.FiltroMaestro, 'tablas_maestras': A.TablaMaestra,
    'reglas_estado_manual': A.ReglaEstadoManual,
    'accesos_proyecto': A.AccesoProyecto, 'kpi_configs': A.KpiConfig,
    'historial_cambios': A.HistorialCambios, 'tecnicos': A.Tecnico,
    'cotizaciones': A.Cotizacion,
}


def _parse_dt(v):
    if v in (None, ''):
        return None
    s = str(v).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f'Fecha no reconocida: {v!r}')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ruta_zip = sys.argv[1]
    if not os.path.isfile(ruta_zip):
        print(f'No existe el archivo: {ruta_zip}')
        sys.exit(1)

    with zipfile.ZipFile(ruta_zip) as zf:
        nombres = zf.namelist()
        manifest = json.loads(zf.read('manifest.json').decode('utf-8')) if 'manifest.json' in nombres else {'tablas': {}}
        datos = {}
        for n in nombres:
            if not n.endswith('.json') or n == 'manifest.json':
                continue
            base = n[:-5]
            tabla = base.rsplit('_p', 1)[0] if '_p' in base and base.rsplit('_p', 1)[1].isdigit() else base
            datos.setdefault(tabla, []).extend(json.loads(zf.read(n).decode('utf-8')))

    print('Tablas en el respaldo:', {k: len(v) for k, v in datos.items()})

    with A.app.app_context():
        A.db.create_all()
        for tabla in ORDEN:
            modelo = MODELOS[tabla]
            filas = datos.get(tabla, [])
            modelo.query.delete()
            cols_dt = {c.name for c in modelo.__table__.columns if isinstance(c.type, A.db.DateTime)}
            for f in filas:
                kw = {}
                for k, v in f.items():
                    if k not in modelo.__table__.columns.keys():
                        continue
                    kw[k] = _parse_dt(v) if k in cols_dt else v
                A.db.session.add(modelo(**kw))
            A.db.session.commit()
            n = modelo.query.count()
            esperado = manifest.get('tablas', {}).get(tabla, '?')
            marca = 'OK' if n == esperado else f'AVISO (respaldo: {esperado})'
            print(f'{tabla}: {n} [{marca}]')

    print('\nListo. Levanta el local con:  python app.py  ->  http://localhost:5001')
    print('Entra con tu mismo usuario/clave de producción. Las fotos no se copiaron (solo datos).')


if __name__ == '__main__':
    main()
