# -*- coding: utf-8 -*-
"""services/pext_reporte.py
Maquetacion del reporte fotografico PEXT (plantilla Excel de 26 fotografias).

Solo describe/lee la plantilla y encaja fotos dentro de sus cuadros: no accede
a HTTP, a la base de datos ni al almacenamiento de evidencia. Se separo de
`apoyo.py` para que la generacion del Excel no dependa del codigo de B2/OneDrive.
"""
import io
import os
import re

from PIL import Image

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# ── Plantilla y slots del reporte ──────────────────────────────────────────
# PEXT: reporte fotográfico estilo Excel de 26 fotografías (solo PEXT usa 'pex').
EVIDENCIA_MAX_PEX = 26
# Plantilla del reporte fotográfico de PEXT (formato del Excel del cliente).
PEX_REPORTE_XLSX = os.path.join(BASE_DIR, 'REPORTE FOTOGRAFICO _ CORRECTIVOS.xlsx')

# Slots del reporte: (titulo, observacion por defecto). 13 pares (izq/der) = 26.
PEX_SLOTS = [
    ("FOTOGRAFIA 01 - ACTIVACION DE CUADRILLA", "Foto de cuadrilla y vehiculo"),
    ("FOTOGRAFIA 03 - INICIO DE MOVILIZACION", "Foto de recorrido hacia el punto de averia"),
    ("FOTOGRAFIA 05 - REPORTE DE INCIDENCIA", "Foto de la infraestructura antes de intervenir"),
    ("FOTOGRAFIA 07 - DIAGNOSTICO", "Falla encontrada, elemento afectado y/o causa preliminar"),
    ("FOTOGRAFIA 09 - PRUEBAS INICIALES", "Potencia, OTDR/VFL"),
    ("FOTOGRAFIA 11 - EJECUCION DEL CORRECTIVO", "Detallar actividades realizadas"),
    ("FOTOGRAFIA 13 - EJECUCION DEL CORRECTIVO", "Detallar actividades realizadas"),
    ("FOTOGRAFIA 17 - MATERIAL UTILIZADO", "Describir el material utilizado"),
    ("FOTOGRAFIA 19 - MATERIAL UTILIZADO", "Describir el material utilizado"),
    ("FOTOGRAFIA 21 - PRUEBAS FINALES", "Valores de Potencia y OTDR posterior al correctivo."),
    ("FOTOGRAFIA 23 - SERVICIO EN UP", ""),
    ("FOTOGRAFIA 25 - CIERRE DEL SITE", "Puertas, camaras, mufas, NAP, etc correctamente cerradas"),
    ("FOTOGRAFIA 27 - DEVOLUCION DE LLAVE", ""),
    ("FOTOGRAFIA 02 - RECOJO DE LLAVES", "Foto de llave + registro de entrega"),
    ("FOTOGRAFIA 04 - ARRIVO AL PUNTO", "Foto de llegada al Site"),
    ("FOTOGRAFIA 06 - REPORTE DE INCIDENCIA", "Foto de la infraestructura antes de intervenir"),
    ("FOTOGRAFIA 08 - DIAGNOSTICO", "Detallar falla encontrada, elemento afectado y/o causa preliminar"),
    ("FOTOGRAFIA 10 - PRUEBAS INICIALES", "Potencia, OTDR/VFL"),
    ("FOTOGRAFIA 12 - EJECUCION DEL CORRECTIVO", "Detallar actividades realizadas"),
    ("FOTOGRAFIA 14 - EJECUCION DEL CORRECTIVO", "Detallar actividades realizadas"),
    ("FOTOGRAFIA 18 - MATERIAL UTILIZADO", "Describir el material utilizado"),
    ("FOTOGRAFIA 20 - MATERIAL UTILIZADO", "Describir el material utilizado"),
    ("FOTOGRAFIA 22 - PRUEBAS FINALES", "Valores de Potencia y OTDR posterior al correctivo."),
    ("FOTOGRAFIA 24 - ORDEN Y LIMPIEZA", ""),
    ("FOTOGRAFIA 26 - CIERRE DEL SITE", "Puertas, camaras, mufas, NAP, etc correctamente cerradas"),
    ("FOTOGRAFIA 25 - CIERRE DE ATENCION", ""),
]
# Celda donde anclar la foto en cada slot (misma posición que el Excel).
PEX_ANCHORS = (
    'A9', 'A18', 'A27', 'A36', 'A45', 'A54', 'A63', 'A72', 'A81', 'A90', 'A99', 'A108', 'A117',
    'H9', 'H18', 'H27', 'H36', 'H45', 'H54', 'H63', 'H72', 'H81', 'H90', 'H99', 'H108', 'H117',
)
# Celda de observaciones de cada slot.
PEX_OBS_CELLS = (
    'A14', 'A23', 'A32', 'A41', 'A50', 'A59', 'A68', 'A77', 'A86', 'A95', 'A104', 'A113', 'A122',
    'H14', 'H23', 'H32', 'H41', 'H50', 'H59', 'H68', 'H77', 'H86', 'H95', 'H104', 'H113', 'H122',
)
def _box_px(ws, min_row, max_row, min_col, max_col):
    """Tamaño aproximado en px del área de celdas del cuadro para encajar la foto."""
    from openpyxl.utils import get_column_letter
    w = 0.0
    for ci in range(min_col, max_col + 1):
        letter = get_column_letter(ci)
        wd = ws.column_dimensions[letter].width if letter in ws.column_dimensions else None
        w += (wd if wd else 8.43) * 7 + 5
    h = 0.0
    for ri in range(min_row, max_row + 1):
        ht = ws.row_dimensions[ri].height if ri in ws.row_dimensions else None
        h += (ht if ht else 15.0) * 4.0 / 3.0
    return w, h


def _n_a_en_box(ws, top, bottom, col0, col1):
    """Escribe 'N/A' centrado en el interior del cuadro cuando la foto no aplica."""
    from openpyxl.styles import Alignment, Font
    row = (top + bottom) // 2
    if col1 - col0 >= 2:
        ws.merge_cells(start_row=row, start_column=col0 + 1,
                       end_row=row, end_column=col1 - 1)
    cell = ws.cell(row=row, column=col0 + 1)
    cell.value = 'N/A'
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.font = Font(size=16, bold=True, color='FF8C8C8C')


def _encajar_foto_cover(bytes_img, box_w, box_h, margen=4):
    """Escala para que la foto ocupe el cuadro respetando el borde rojo.
    Mantiene la proporción (vertical/horizontal) y ajusta al interior del cuadro."""
    try:
        im = Image.open(io.BytesIO(bytes_img))
        iw, ih = im.size
    except Exception:
        iw, ih = 800, 600
    eff_w = max(box_w - margen * 2, 40)
    eff_h = max(box_h - margen * 2, 40)
    ratio = min(eff_w / iw, eff_h / ih, 1.0)
    # si la imagen es más chica que el cuadro, escala hasta llenarlo proporcionalmente
    if iw < eff_w and ih < eff_h:
        ratio = min(eff_w / iw, eff_h / ih)
    return max(1, int(iw * ratio)), max(1, int(ih * ratio))


def _pext_config():
    """Lee la plantilla y devuelve los slots del reporte en orden de exportación
    (columna izquierda de arriba a abajo, luego columna derecha). Robustez: se
    adapta a cajas/títulos/observaciones que edite el usuario en el Excel."""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    wb = load_workbook(PEX_REPORTE_XLSX)
    ws = wb.worksheets[0]
    bands = [('L', 1, 6), ('R', 8, 13)]
    titles = {'L': [], 'R': []}
    obs_rows = {'L': [], 'R': []}
    boxes = {'L': [], 'R': []}
    for rng in ws.merged_cells.ranges:
        band = None
        for k, c0, c1 in bands:
            if (rng.min_row == rng.max_row
                    and rng.min_col <= c0 and rng.max_col >= c1):
                band = k
                break
        if band:
            v = ws.cell(row=rng.min_row, column=rng.min_col).value
            v = (v or '').strip() if v is not None else ''
            if re.match(r'^FOTOGRAFIA\b', v, re.I):
                titles[band].append(rng.min_row)
            elif re.match(r'^OBSERVACION', v, re.I):
                obs_rows[band].append(rng.min_row)
        else:
            for k, c0, c1 in bands:
                if (rng.max_row - rng.min_row) >= 3 and rng.min_col <= c0 and rng.max_col >= c1:
                    boxes[k].append(rng)
                    break
    slots = []
    for k, c0, c1 in bands:
        titles[k].sort()
        obs_rows[k].sort()
        for trow in titles[k]:
            titulo = (ws.cell(row=trow, column=c0).value or '').strip()
            top = trow + 1
            bottom = None
            for o in obs_rows[k]:
                if o > trow:
                    bottom = o - 1
                    break
            for rng in boxes[k]:
                if rng.min_row == trow + 1:
                    bottom = rng.max_row
                    break
            if bottom is None:
                bottom = top + 4
            obs_def = ''
            for o in obs_rows[k]:
                if o == bottom + 1:
                    ov = (ws.cell(row=o, column=c0).value or '').strip()
                    ov = re.sub(r'^OBSERVACIONES?\s*:?\s*', '', ov, flags=re.I)
                    obs_def = ov
                    break
            slots.append({
                'anchor': get_column_letter(c0) + str(top),
                'titulo': titulo,
                'obs': obs_def,
                'top': top,
                'bottom': bottom,
                'col0': c0,
                'col1': c1,
            })
    if not slots:
        return _pext_config_cajas(wb)
    maxnum = 0
    for s in slots:
        m = re.search(r'FOTOGRAFIA\s+(\d+)', s['titulo'])
        if m:
            maxnum = max(maxnum, int(m.group(1)))
    for s in slots:
        if not s['titulo']:
            maxnum += 1
            s['titulo'] = f'FOTOGRAFIA {maxnum}'
    return slots


def _pext_config_cajas(wb):
    """Fallback: slots detectados por cajas fusionadas (sin títulos/obs)."""
    from openpyxl.utils import get_column_letter
    ws = wb.worksheets[0]
    left, right = [], []
    for rng in ws.merged_cells.ranges:
        if (rng.max_row - rng.min_row) == 3:
            if rng.min_col <= 1 and rng.max_col >= 6:
                left.append(rng)
            elif rng.min_col <= 8 and rng.max_col >= 13:
                right.append(rng)
    left.sort(key=lambda r: r.min_row)
    right.sort(key=lambda r: r.min_row)
    slots = []
    for rng in list(left) + list(right):
        band = 1 if rng.min_col <= 6 else 8
        titulo = (ws.cell(row=rng.min_row - 2, column=band).value or '').strip()
        obs_def = ''
        for mr in ws.merged_cells.ranges:
            if (mr.min_row == rng.max_row + 2
                    and mr.min_col <= rng.max_col and mr.max_col >= rng.min_col):
                v = (ws.cell(row=mr.min_row, column=mr.min_col).value or '').strip()
                if v.startswith('OBSERVACIONES:'):
                    v = v[len('OBSERVACIONES:'):].strip()
                obs_def = v
                break
        slots.append({
            'anchor': rng.coord.split(':')[0],
            'titulo': titulo,
            'obs': obs_def,
            'top': rng.min_row,
            'bottom': rng.max_row,
            'col0': rng.min_col,
            'col1': rng.max_col,
        })
    return slots


def _pext_max():
    try:
        return len(_pext_config())
    except Exception:
        return EVIDENCIA_MAX_PEX

