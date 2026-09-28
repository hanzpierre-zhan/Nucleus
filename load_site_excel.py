# -*- coding: utf-8 -*-
"""Carga el maestro SITE desde el Excel COBRA SITES (Site.xlsx) a la BD.

Uso:
    python load_site_excel.py [ruta_al_excel]

Reemplaza TODOS los sites del proyecto 'SITE' por las filas del Excel
(default: C:\\Mega\\Nucleus\\Site.xlsx). Hace un backup previo de la BD en
backups\\ antes de borrar. La configuración de columnas la aplica
migrations/run_migrations al arrancar la app (20 columnas del formato).
"""
import os
import re
import sys
import json
import shutil
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

RUTA_DEFECTO = r'C:\Mega\Nucleus\Site.xlsx'
PROYECTO = 'SITE'


def _norm(s):
    """Nombre de columna normalizado (sin acentos/tildes) para mapear el Excel."""
    out = []
    for ch in str(s or '').strip().lower():
        out.append({'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
                    'ö': 'o', 'ü': 'u', 'ñ': 'n', '(': ' ', ')': ' ',
                    '°': ' ', "'": ' '}.get(ch, ch))
    return ''.join(out).replace('  ', ' ').strip()


def _celda(val):
    """Normaliza el valor de una celda a texto limpio ('' si nulo)."""
    if val is None:
        return ''
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def _leer_excel(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else '' for h in next(rows)]
    idx = {_norm(name): i for i, name in enumerate(headers)}
    ci = idx.get('codigo')
    if ci is None:
        raise RuntimeError('No se encontró la columna "Código" en el Excel.')
    registros = {}
    order = []
    vacios = 0
    for r in rows:
        if not any(r):
            continue
        cod = _celda(r[ci])
        if not cod:
            vacios += 1
            continue
        data = {name: _celda(r[i]) for i, name in enumerate(headers)}
        # duplicados: gana la última aparición
        if cod not in registros:
            order.append(cod)
        registros[cod] = data
    return headers, registros, order, vacios


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else RUTA_DEFECTO
    if not os.path.exists(path):
        sys.exit(f'No existe el Excel: {path}')
    headers, registros, order, vacios = _leer_excel(path)
    print(f'Excel: {path}  ({len(headers)} columnas, {len(order)} sites, '
          f'{len(registros) - len(order)} duplicados saltados, '
          f'{vacios} filas sin código)')

    from app import app, db
    from models import Proyecto, NucleusData

    with app.app_context():
        proy = Proyecto.query.filter_by(nombre=PROYECTO).first()
        if not proy:
            sys.exit('No existe el proyecto SITE.')
        pid = proy.id

        if os.environ.get('SKIP_BACKUP', '').lower() not in ('1', 'true'):
            bdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
            os.makedirs(bdir, exist_ok=True)
            stamp = datetime.now().strftime('pre_site_load_%Y%m%d_%H%M%S')
            src = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
            m = re.search(r'sqlite:///(.+)$', src)
            if m and os.path.exists(m.group(1)):
                dst = os.path.join(bdir, os.path.basename(m.group(1)).rsplit('.', 1)[0] + f'_{stamp}.db')
                shutil.copyfile(m.group(1), dst)
                print(f'Backup: {dst}')
            else:
                # BD remota (Postgres/Neon): exporta los registros actuales a JSON
                filas = [{'key_value': r.key_value, 'data_json': r.data_json}
                         for r in NucleusData.query.filter_by(proyecto_id=pid).all()]
                dst = os.path.join(bdir, f'site_previo_{stamp}.json')
                with open(dst, 'w', encoding='utf-8') as fh:
                    json.dump(filas, fh, ensure_ascii=False)
                print(f'Backup JSON ({len(filas)} filas): {dst}')

        antiguo = NucleusData.query.filter_by(proyecto_id=pid).count()
        NucleusData.query.filter_by(proyecto_id=pid).delete()
        db.session.commit()

        nuevos = []
        for cod in order:
            nuevos.append(NucleusData(proyecto_id=pid, key_value=cod,
                                      data_json=json.dumps(registros[cod],
                                                           ensure_ascii=False)))
        db.session.add_all(nuevos)
        db.session.commit()

        final = NucleusData.query.filter_by(proyecto_id=pid).count()
        print(f'Proyecto SITE: {antiguo} -> {final} sites cargados.')


if __name__ == '__main__':
    main()