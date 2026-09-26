# -*- coding: utf-8 -*-
"""services/apoyo.py
Helpers portados desde el monolito (backup_20260925_124858/app.py): evidencia,
B2/OneDrive, reporte fotográfico PEXT, cotizaciones PDF y sync FLM.
No contiene rutas HTTP. Usa `current_app` en lugar del `app` del monolito.
"""
import io
import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime

from flask import current_app, session, request, jsonify, make_response
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

from db import db
from models import (Proyecto, AppConfig, TokenStore, NucleusData,
                    NucleusHistory, FiltroMaestro, TablaMaestra,
                    ReglaEstadoManual, AccesoProyecto, KpiConfig,
                    HistorialCambios, Tecnico, Cotizacion)

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# ── Evidencia: constantes ──────────────────────────────────────────────────
EVIDENCIA_TIPOS = ('inicio', 'proceso', 'cierre')
EVIDENCIA_MAX_POR_TIPO = 5
# PEXT: reporte fotográfico estilo Excel de 26 fotografías (solo PEXT usa 'pex').
EVIDENCIA_MAX_PEX = 26
# Resguardo: 2 fotos (inicio / fin) en pestaña propia antes de Evidencia
EVIDENCIA_TIPO_RESGUARDO = 'resguardo'
EVIDENCIA_MAX_RESGUARDO = 2
EVIDENCIA_EXT_ALLOWED = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic'}

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


def evidencia_folder(pid, key):
    return os.path.join(current_app.config['EVIDENCIA_DIR'], str(pid), secure_filename(str(key)))


def evidencia_limpiar_slot(pid, key, tipo, indice):
    import glob
    folder = evidencia_folder(pid, key)
    for old in glob.glob(os.path.join(folder, f'{tipo}_{int(indice)}.*')):
        try:
            os.remove(old)
        except Exception:
            pass


def evidencia_comprimir(ruta, calidad=None, max_lado=None):
    """Comprime y redimensiona una imagen para ahorrar almacenamiento.
    Devuelve True si se comprimió correctamente; si no puede (ej. HEIC),
    deja el archivo original tal cual."""
    calidad = calidad if calidad is not None else current_app.config['EVIDENCIA_CALIDAD']
    max_lado = max_lado if max_lado is not None else current_app.config['EVIDENCIA_MAX_LADO']
    try:
        img = Image.open(ruta)
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert('RGB')
        w, h = img.size
        lado_max = max(w, h)
        if lado_max > max_lado:
            ratio = max_lado / lado_max
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
        img.save(ruta, 'JPEG', quality=calidad, optimize=True)
        return True
    except Exception:
        return False


def evidencia_usa_b2():
    return bool(current_app.config.get('B2_BUCKET') and current_app.config.get('B2_KEY_ID') and current_app.config.get('B2_APP_KEY'))


def b2_cliente():
    import boto3
    endpoint = current_app.config['B2_ENDPOINT_URL'] or f"https://s3.{current_app.config['B2_REGION']}.backblazeb2.com"
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=current_app.config['B2_KEY_ID'],
        aws_secret_access_key=current_app.config['B2_APP_KEY'],
        region_name=current_app.config['B2_REGION'],
    )


def evidencia_eliminar_b2(key, tipo, indice):
    client = b2_cliente()
    bucket = current_app.config['B2_BUCKET']
    prefix = f'{key}/{tipo}_{int(indice)}.'
    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for o in resp.get('Contents', []):
            client.delete_object(Bucket=bucket, Key=o['Key'])
    except Exception:
        pass


# ── OneDrive personal (2do backup, Microsoft Graph) ────────────────────────
OD_GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
OD_TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'


def _od_cuenta(num):
    """Config de la cuenta OneDrive num (1 = principal, 2 = adicional)."""
    if num == 1:
        return {
            'client_id': current_app.config.get('OD_CLIENT_ID', ''),
            'client_secret': current_app.config.get('OD_CLIENT_SECRET', ''),
            'refresh': current_app.config.get('OD_REFRESH_TOKEN', ''),
            'enabled': current_app.config.get('OD_ENABLED', False),
            'token_key': 'od_refresh_token',
        }
    return {
        'client_id': current_app.config.get('OD_CLIENT_ID_2', ''),
        'client_secret': current_app.config.get('OD_CLIENT_SECRET_2', ''),
        'refresh': current_app.config.get('OD_REFRESH_TOKEN_2', ''),
        'enabled': current_app.config.get('OD_ENABLED_2', False),
        'token_key': 'od_refresh_token_2',
    }


def _od_refresh_token_guardar(valor, num=1):
    clave = _od_cuenta(num)['token_key']
    try:
        fila = TokenStore.query.filter_by(clave=clave).first()
        if fila:
            fila.valor = valor
        else:
            db.session.add(TokenStore(clave=clave, valor=valor))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.warning('OD: no se pudo persistir el refresh token')


def _od_refresh_token_actual(num=1):
    clave = _od_cuenta(num)['token_key']
    try:
        fila = TokenStore.query.filter_by(clave=clave).first()
        if fila and fila.valor:
            return fila.valor
    except Exception:
        pass
    return _od_cuenta(num).get('refresh', '')


def onedrive_access_token(num=1):
    """Renueva/obtiene el access token de OneDrive. Persiste el refresh rotado."""
    cuenta = _od_cuenta(num)
    refresh = _od_refresh_token_actual(num)
    if not refresh:
        return None
    datos = {
        'client_id': cuenta['client_id'],
        'grant_type': 'refresh_token',
        'refresh_token': refresh,
        'scope': 'Files.ReadWrite offline_access',
    }
    if cuenta.get('client_secret'):
        datos['client_secret'] = cuenta['client_secret']
    body = urllib.parse.urlencode(datos).encode('utf-8')
    req = urllib.request.Request(OD_TOKEN_URL, data=body, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(req, timeout=60) as resp:
        info = json.loads(resp.read().decode('utf-8'))
    if info.get('refresh_token'):
        _od_refresh_token_guardar(info['refresh_token'], num)
    return info.get('access_token')


def _od_url(ruta_remota):
    return OD_GRAPH_BASE + '/me/drive/root:' + ruta_remota


def _onedrive_subir_a(num, b2_key, ruta_local):
    if not _od_cuenta(num).get('enabled'):
        return False
    token = onedrive_access_token(num)
    if not token:
        current_app.logger.warning('OD%d: sin access token, se omite el backup', num)
        return False
    ruta_remota = '/Nucleus/' + '/'.join(
        urllib.parse.quote(seg, safe='') for seg in b2_key.split('/'))
    url = _od_url(ruta_remota) + ':/content'
    with open(ruta_local, 'rb') as f:
        data = f.read()
    req = urllib.request.Request(url, data=data, method='PUT')
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Content-Type', 'image/jpeg')
    with urllib.request.urlopen(req, timeout=120) as resp:
        resp.read()
    return True


def onedrive_subir(b2_key, ruta_local):
    """Sube una foto a todos los OneDrive configurados en /Nucleus/<key>/<nombre>."""
    ok = False
    for num in (1, 2):
        try:
            if _onedrive_subir_a(num, b2_key, ruta_local):
                ok = True
        except Exception as e:
            current_app.logger.warning('OD%d subir fallo: %s', num, e)
    return ok


def _onedrive_eliminar_a(num, key, tipo, indice):
    if not _od_cuenta(num).get('enabled'):
        return False
    token = onedrive_access_token(num)
    if not token:
        return False
    key_san = urllib.parse.quote(secure_filename(str(key)), safe='')
    url_list = _od_url('/Nucleus/' + key_san) + ':/children'
    prefijo = f'{tipo}_{int(indice)}.'
    req = urllib.request.Request(url_list)
    req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            info = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
    for item in info.get('value', []):
        if not str(item.get('name', '')).startswith(prefijo):
            continue
        dreq = urllib.request.Request(
            OD_GRAPH_BASE + '/me/drive/items/' + item['id'], method='DELETE')
        dreq.add_header('Authorization', 'Bearer ' + token)
        urllib.request.urlopen(dreq, timeout=60).read()
    return True


def onedrive_eliminar(key, tipo, indice):
    """Elimina la foto del slot en todos los OneDrive configurados."""
    ok = False
    for num in (1, 2):
        try:
            if _onedrive_eliminar_a(num, key, tipo, indice):
                ok = True
        except Exception as e:
            current_app.logger.warning('OD%d eliminar fallo: %s', num, e)
    return ok


def _evidencia_aprobacion_bloquea(pid, key):
    """El rol Contrata no puede subir/quitar evidencia en WOs (PEXT/FLM) ya enviados a aprobación."""
    if str(session.get('rol') or '').strip().lower() != 'contrata':
        return False
    proy = db.session.get(Proyecto, pid) if pid else None
    if not proy or (proy.nombre or '').strip() not in ('FLM', 'FLM - ENTEL', 'PEXT'):
        return False
    rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=str(key or '')).first()
    if not rec:
        return False
    try:
        d = json.loads(rec.data_json or '{}')
    except Exception:
        d = {}
    return str(d.get('_ENVIADO_APROBACION', '')).strip() == '1'


# ── Migración formato evidencia legacy (26 -> 28) ─────────────────────────
_EVIDENCIA_OLD26_A_NUEVO = {
    0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 11, 12: 12,
    13: 14, 14: 15, 15: 16, 16: 17, 17: 18, 18: 19, 19: 20, 20: 21, 21: 22, 22: 23, 23: 24, 24: 25,
}


def _evidencia_migrar_legacy(d):
    """Reubica la evidencia PEXT del formato anterior (array de 26) al actual (28).
    Solo aplica si `_EVIDENCIA_FOTOS` mide 26; idempotente. Devuelve True si cambió d."""
    if not isinstance(d, dict) or d.get('_EVIDENCIA_LEGACY') == '26':
        return False
    raw = d.get('_EVIDENCIA_FOTOS')
    try:
        fotos = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return False
    if not isinstance(fotos, list) or len(fotos) != 26:
        return False
    for campo in ('_EVIDENCIA_FOTOS', '_EVIDENCIA_OBS', '_EVIDENCIA_APLICA'):
        rawf = d.get(campo)
        try:
            arr = json.loads(rawf) if isinstance(rawf, str) else rawf
        except Exception:
            arr = None
        if not isinstance(arr, list) or len(arr) != 26:
            continue
        nuevo = [''] * 28
        for i, v in enumerate(arr[:26]):
            j = _EVIDENCIA_OLD26_A_NUEVO.get(i)
            if j is not None and v not in (None, ''):
                nuevo[j] = v
        d[campo] = json.dumps(nuevo, ensure_ascii=False)
    d['_EVIDENCIA_LEGACY'] = '26'
    return True


# ── Lectura de evidencia (local/B2) y PEXT ────────────────────────────────
def _evidencia_leer(pid, key, nombre):
    """Devuelve los bytes de un archivo de evidencia (local o B2), o None."""
    if evidencia_usa_b2():
        try:
            obj = b2_cliente().get_object(Bucket=current_app.config['B2_BUCKET'], Key=f'{key}/{nombre}')
            return obj['Body'].read()
        except Exception:
            return None
    ruta = os.path.join(evidencia_folder(pid, key), nombre)
    try:
        with open(ruta, 'rb') as f:
            return f.read()
    except Exception:
        return None


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


# ── PDFs de cotización ─────────────────────────────────────────────────────
def _fecha_larga_es(fecha=None):
    """Fecha en formato largo español: 'viernes, 21 de Agosto de 2026'."""
    DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
             'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    f = fecha or datetime.now()
    return f'{DIAS[f.weekday()]}, {f.day} de {MESES[f.month - 1]} de {f.year}'


def _generar_pdf_cotizacion(numero, nota, ticket, cotizado_por, revisado_por, fecha, gastos, mano_obra):
    """Genera el PDF de cotización con el formato exacto de la imagen."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    PAGE_W, PAGE_H = landscape(A4)
    M = 6 * mm  # margen

    # Colores corporativos
    NAVY = colors.HexColor('#1B3A6B')
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor('#F2F2F2')
    MID_GRAY = colors.HexColor('#D9D9D9')
    DARK = colors.HexColor('#1a1a1a')

    def fmt_soles(v):
        try:
            f = float(v)
            return f'S/ {f:,.2f}'
        except Exception:
            return 'S/ -'

    def safe_str(v):
        return str(v) if v is not None else ''

    # Calcular subtotales
    subtotal_a = sum(float(g.get('total_p', 0) or 0) for g in gastos)
    subtotal_b = sum(float(m.get('total_p', 0) or 0) for m in mano_obra)
    total_ab = subtotal_a + subtotal_b

    # Estilos de párrafo
    style_normal = ParagraphStyle('normal', fontName='Helvetica', fontSize=7, leading=8)
    style_bold = ParagraphStyle('bold', fontName='Helvetica-Bold', fontSize=7, leading=8)
    style_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=NAVY)
    style_header_white = ParagraphStyle('hw', fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=WHITE)
    style_section = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=WHITE)
    style_right = ParagraphStyle('right', fontName='Helvetica', fontSize=7, leading=8, alignment=TA_RIGHT)
    style_right_bold = ParagraphStyle('rb', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                             leftMargin=M, rightMargin=M,
                             topMargin=M, bottomMargin=M)
    W = PAGE_W - 2 * M
    story = []

    # ---- CABECERA: Logo | N° Cotización ---
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'cobra-logo.png')
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=30*mm, height=17*mm)
    else:
        logo = Paragraph('<b>cobra</b>', style_title)

    num_para = Paragraph(f'<b>N° Cotización :&nbsp;&nbsp;&nbsp;{numero}</b>', style_title)
    header_data = [[logo, num_para]]
    header_tbl = Table(header_data, colWidths=[W * 0.4, W * 0.6])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 1.5 * mm))

    # ---- SECCIÓN A: DATOS DEL CLIENTE ---
    def section_row(label):
        return [Paragraph(f'<b>{label}</b>', style_header_white), '', '', '']

    def client_row(label, value, label2='', value2=''):
        cells = [
            Paragraph(f'<b>{label}</b>', style_bold),
            Paragraph(safe_str(value), style_normal),
            Paragraph(f'<b>{label2}</b>', style_bold) if label2 else '',
            Paragraph(safe_str(value2), style_normal) if value2 else '',
        ]
        return cells

    c1 = W * 0.18
    c2 = W * 0.42
    c3 = W * 0.12
    c4 = W * 0.28

    sec_a_data = [
        [Paragraph('<b>A: DATOS DEL CLIENTE</b>', style_header_white), '', '', ''],
        client_row('Cliente:', 'HUAWEI DEL PERU', 'RUC:', '20507646728'),
        client_row('Domicilio:', 'Cal. las Begonias Nro. 415 Int. 2301'),
        client_row('Solicitado por:', 'Even Vivar'),
        client_row('Validador:', 'Sergio Huaman'),
        client_row('Nota:', nota or ''),
    ]
    sec_a_tbl = Table(sec_a_data, colWidths=[c1, c2, c3, c4])
    sec_a_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('SPAN', (0, 0), (-1, 0)),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (1, 2), (3, 2)),
        ('SPAN', (1, 3), (3, 3)),
        ('SPAN', (1, 4), (3, 4)),
        ('SPAN', (1, 5), (3, 5)),
    ]))
    story.append(sec_a_tbl)
    story.append(Spacer(1, 1 * mm))

    # ---- SECCIÓN B: DATOS DE COTIZACIÓN ---
    sec_b_data = [
        [Paragraph('<b>B: DATOS DE COTIZACION</b>', style_header_white), '', '', ''],
        client_row('Cotizado por:', 'Dennis Unton', 'Fecha:', fecha),
        client_row('Revisado por:', 'Dennis Unton', 'Fecha:', fecha),
    ]
    sec_b_tbl = Table(sec_b_data, colWidths=[c1, c2, c3, c4])
    sec_b_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('SPAN', (0, 0), (-1, 0)),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sec_b_tbl)
    story.append(Spacer(1, 1 * mm))

    # ---- TABLA 1: Materiales, Herramientas y/o Homologaciones ---
    col_item = W * 0.06
    col_cod = W * 0.07
    col_desc = W * 0.30
    col_unid = W * 0.07
    col_cant = W * 0.08
    col_pu = W * 0.18
    col_tp = W * 0.24

    t1_cols = [col_item, col_cod, col_desc, col_unid, col_cant, col_pu, col_tp]

    t1_header_sub = [Paragraph('<b>1. Materiales,  Herramientas y/o Homologaciones</b>', style_section), '', '', '', '', '', '']
    t1_col_header = [
        Paragraph('<b>Item</b>', style_bold),
        Paragraph('<b>Cod.</b>', style_bold),
        Paragraph('<b>Descripción</b>', style_bold),
        Paragraph('<b>Unid</b>', style_bold),
        Paragraph('<b>Cant</b>', style_bold),
        Paragraph('<b>Precio unid.</b>', style_bold),
        Paragraph('<b>Total P.</b>', style_bold),
    ]

    t1_rows = [t1_header_sub, t1_col_header]
    MAX_ROWS_1 = max(len(gastos), 2)
    for i in range(MAX_ROWS_1):
        if i < len(gastos):
            g = gastos[i]
            row = [
                Paragraph(safe_str(g.get('item', i+1)), style_normal),
                Paragraph(safe_str(g.get('cod', 'SC')), style_normal),
                Paragraph(safe_str(g.get('descripcion', '')), style_normal),
                Paragraph(safe_str(g.get('unid', '')), style_normal),
                Paragraph(safe_str(g.get('cant', '')), style_normal),
                Paragraph(fmt_soles(g.get('precio_unid', '')), style_right),
                Paragraph(fmt_soles(g.get('total_p', '')), style_right),
            ]
        else:
            row = ['', '', '', '', '', Paragraph('S/', style_right), Paragraph('-', style_right)]
        t1_rows.append(row)

    # Fila Total subtotal A
    t1_rows.append(['', '', '', '', '', '', ''])
    t1_rows.append([
        Paragraph('<b>Total</b>', style_bold), '', '', '', '', '',
        Paragraph(f'<b>Subtotal_A&nbsp;&nbsp;&nbsp;{fmt_soles(subtotal_a)}</b>', style_right_bold),
    ])

    t1_tbl = Table(t1_rows, colWidths=t1_cols)
    n_data_rows_1 = len(t1_rows)
    t1_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 2), (-1, n_data_rows_1-3), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, n_data_rows_1-1), (-1, n_data_rows_1-1), LIGHT_GRAY),
        ('SPAN', (0, n_data_rows_1-1), (4, n_data_rows_1-1)),
        ('SPAN', (5, n_data_rows_1-1), (5, n_data_rows_1-1)),
    ]
    t1_tbl.setStyle(TableStyle(t1_style))
    story.append(t1_tbl)
    story.append(Spacer(1, 1.5 * mm))

    # ---- TABLA 2: Mano de Obra ---
    t2_cols = [col_item, col_cod, col_desc, col_unid, col_cant, col_pu, col_tp]

    t2_header_sub = [Paragraph('<b>2. Mano de Obra</b>', style_section), '', '', '', '', '', '']
    t2_col_header = [
        Paragraph('<b>Item</b>', style_bold),
        Paragraph('<b>Cod.</b>', style_bold),
        Paragraph('<b>Descripción</b>', style_bold),
        Paragraph('<b>Unid</b>', style_bold),
        Paragraph('<b>Cant</b>', style_bold),
        Paragraph('<b>Precio unid.</b>', style_bold),
        Paragraph('<b>Total P.</b>', style_bold),
    ]

    t2_rows = [t2_header_sub, t2_col_header]
    MAX_ROWS_2 = max(len(mano_obra), 2)
    for i in range(MAX_ROWS_2):
        if i < len(mano_obra):
            m = mano_obra[i]
            row = [
                Paragraph(safe_str(m.get('item', i+1)), style_normal),
                Paragraph(safe_str(m.get('cod', 'SC')), style_normal),
                Paragraph(safe_str(m.get('descripcion', '')), style_normal),
                Paragraph(safe_str(m.get('unid', '')), style_normal),
                Paragraph(safe_str(m.get('cant', '')), style_normal),
                Paragraph(fmt_soles(m.get('precio_unid', '')), style_right),
                Paragraph(fmt_soles(m.get('total_p', '')), style_right),
            ]
        else:
            row = ['', '', '', '', '', '', '']
        t2_rows.append(row)

    t2_rows.append([
        Paragraph('<b>Total</b>', style_bold), '', '', '', '', '',
        Paragraph(f'<b>Subtotal_B&nbsp;&nbsp;&nbsp;{fmt_soles(subtotal_b)}</b>', style_right_bold),
    ])

    t2_tbl = Table(t2_rows, colWidths=t2_cols)
    n_data_rows_2 = len(t2_rows)
    t2_style = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 2), (-1, n_data_rows_2-2), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, n_data_rows_2-1), (-1, n_data_rows_2-1), LIGHT_GRAY),
        ('SPAN', (0, n_data_rows_2-1), (5, n_data_rows_2-1)),
    ]
    t2_tbl.setStyle(TableStyle(t2_style))
    story.append(t2_tbl)
    story.append(Spacer(1, 2 * mm))

    # ---- CONDICIONES COMERCIALES + TOTAL FINAL ---
    try:
        total_val = f'{total_ab:,.2f}'
    except Exception:
        total_val = '0.00'

    cond_col_left = W * 0.50
    cond_col_mid = W * 0.25
    cond_col_soles = W * 0.07
    cond_col_monto = W * 0.18

    style_cond_hdr = ParagraphStyle('condh', fontName='Helvetica-Bold', fontSize=7, leading=9)
    style_cond_body = ParagraphStyle('condb', fontName='Helvetica', fontSize=7, leading=10)
    style_total_label = ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER)
    style_soles = ParagraphStyle('sol', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER)
    style_monto = ParagraphStyle('mnt', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_RIGHT)

    cond_lines = 'Moneda Nacional soles (S/)<br/>Pagos Según contrato<br/>No incluye IGV'
    cond_data = [
        [
            Paragraph('<b>Condiciones Comerciales</b>', style_cond_hdr),
            '', '', ''
        ],
        [
            Paragraph(cond_lines, style_cond_body),
            Paragraph('<b>Total Cotización (A+B)</b>', style_total_label),
            Paragraph('<b>S/</b>', style_soles),
            Paragraph(f'<b>{total_val}</b>', style_monto),
        ],
    ]
    cond_tbl = Table(cond_data, colWidths=[cond_col_left, cond_col_mid, cond_col_soles, cond_col_monto])
    cond_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.3, MID_GRAY),
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_GRAY),
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 1), (0, 1), WHITE),
        ('BACKGROUND', (1, 1), (3, 1), LIGHT_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 1), (3, 1), 'RIGHT'),
    ]))
    story.append(cond_tbl)

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _generar_pdf_cotizacion_cobra(numero, site, supervisor, objetivo, ticket, elaborado_por, items):
    """
    Genera el PDF de cotizacion FLM con el formato Cobra:
    cabecera (FECHA/EMPRESA/DIRIGIDO A/SITE/N COTIZACION/OBJETIVO + RESPONSABLE/
    ELABORADO POR/SUPERVISOR/TICKET), tabla unica de items con FEE y secciones
    fijas de cierre.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    PAGE_W, PAGE_H = landscape(A4)
    M = 8 * mm

    NAVY = colors.HexColor('#1F4E79')
    STEEL = colors.HexColor('#2E75B6')
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor('#F2F2F2')
    MID_GRAY = colors.HexColor('#BFBFBF')
    YELLOW = colors.HexColor('#FFF2CC')
    DARK = colors.HexColor('#1a1a1a')

    def safe_str(v):
        return str(v) if v is not None else ''

    def fmt_soles(v):
        try:
            return f'S/ {float(v):,.2f}'
        except Exception:
            return 'S/ 0.00'

    def fmt_num(v):
        try:
            f = float(v)
            return ('%g' % f) if f == int(f) else f'{f:,.2f}'
        except Exception:
            return ''

    # ---- Estilos ----
    st_norm = ParagraphStyle('n', fontName='Helvetica', fontSize=8, leading=10)
    st_bold = ParagraphStyle('b', fontName='Helvetica-Bold', fontSize=8, leading=10)
    st_hdr_w = ParagraphStyle('hw', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=WHITE)
    st_sec = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=DARK)
    st_cell_c = ParagraphStyle('cc', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_CENTER)
    st_cell_r = ParagraphStyle('cr', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=M, rightMargin=M,
                            topMargin=M, bottomMargin=M)
    W = PAGE_W - 2 * M
    story = []

    # ---- LOGO + Supplier name and RUC No ----
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'cobra-logo.png')
    logo_cell = []
    if os.path.exists(logo_path):
        logo_cell.append(RLImage(logo_path, width=42 * mm, height=20 * mm))
    else:
        logo_cell.append(Paragraph('<b>cobra</b>', ParagraphStyle(
            'lg', fontName='Helvetica-Bold', fontSize=22, leading=24, textColor=NAVY)))
    logo_cell.append(Paragraph('COBRA PERU S.A.C. — RUC 20253881438', ParagraphStyle(
        'ruc', fontName='Helvetica', fontSize=7, leading=9, textColor=colors.HexColor('#333333'))))

    fecha_str = _fecha_larga_es()
    num_para = Paragraph(f'<b>N° COTIZACIÓN :&nbsp;&nbsp;&nbsp;&nbsp;{safe_str(numero)}</b>',
                         ParagraphStyle('np', fontName='Helvetica-Bold', fontSize=12, leading=15))
    head_tbl = Table([[logo_cell, num_para]], colWidths=[W * 0.45, W * 0.55])
    head_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(head_tbl)
    story.append(Spacer(1, 2 * mm))

    # ---- CABECERA DE DATOS (4 columnas) ----
    c1, c2, c3, c4 = W * 0.14, W * 0.36, W * 0.14, W * 0.36

    def row_lbl(lbl, val, lbl2='', val2=''):
        return [
            Paragraph(f'<b>{lbl}</b>', st_bold),
            Paragraph(safe_str(val), st_norm),
            Paragraph(f'<b>{lbl2}</b>', st_bold) if lbl2 else '',
            Paragraph(safe_str(val2), st_norm) if val2 else '',
        ]

    hdr_data = [
        row_lbl('FECHA:', fecha_str),
        row_lbl('EMPRESA:', 'Cobra Perú'),
        row_lbl('DIRIGIDO A :', 'Huawei del Perú', 'RESPONSABLE', 'Dennis Unton'),
        row_lbl('SITE:', site, 'ELABORADO POR', elaborado_por),
        row_lbl('N° COTIZACIÓN :', numero, 'SUPERVISOR', supervisor),
        row_lbl('OBJETIVO:', objetivo, 'TICKET', ticket),
    ]
    hdr_tbl = Table(hdr_data, colWidths=[c1, c2, c3, c4])
    hdr_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, MID_GRAY),
        ('BACKGROUND', (0, 0), (0, -1), LIGHT_GRAY),
        ('BACKGROUND', (2, 0), (2, -1), LIGHT_GRAY),
        # N° COTIZACION resaltado en amarillo
        ('BACKGROUND', (0, 4), (1, 4), YELLOW),
        ('SPAN', (1, 0), (3, 0)),   # FECHA valor ancho
        ('SPAN', (1, 1), (3, 1)),   # EMPRESA valor ancho
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 3 * mm))

    # ---- TABLA DE ITEMS ---- (ajustado para que REEMBOLSABLE no se corte)
    col_correl = W * 0.065
    col_tipo = W * 0.11
    col_texto = W * 0.26
    col_und = W * 0.055
    col_cant = W * 0.065
    col_vu = W * 0.10
    col_fee = W * 0.06
    col_vt = W * 0.115
    col_coment = W * 0.17
    it_cols = [col_correl, col_tipo, col_texto, col_und, col_cant, col_vu, col_fee, col_vt, col_coment]

    it_header = [
        Paragraph('<b>CORRELATIVO</b>', st_hdr_w),
        Paragraph('<b>TIPO</b>', st_hdr_w),
        Paragraph('<b>TEXTO EXPLICATIVO</b>', st_hdr_w),
        Paragraph('<b>UND</b>', st_hdr_w),
        Paragraph('<b>CANTIDAD</b>', st_hdr_w),
        Paragraph('<b>VALOR UNITARIO</b>', st_hdr_w),
        Paragraph('<b>FEE %</b>', st_hdr_w),
        Paragraph('<b>VALOR TOTAL</b>', st_hdr_w),
        Paragraph('<b>COMENTARIOS</b>', st_hdr_w),
    ]

    it_rows = [it_header]
    items_ok = []
    for i, it in enumerate(items or []):
        try:
            cant = float(str(it.get('cantidad', '') or 0).replace(',', '.'))
        except Exception:
            cant = 0.0
        try:
            vu = float(str(it.get('valor_unitario', '') or 0).replace(',', '.'))
        except Exception:
            vu = 0.0
        tipo = str(it.get('tipo', '') or '').strip().upper()
        fee = 5.0 if tipo == 'REEMBOLSABLE' else 0.0
        vt = cant * vu * (1 + fee / 100.0)
        items_ok.append(vt)
        it_rows.append([
            Paragraph(str(i + 1), st_cell_c),
            Paragraph(safe_str(tipo), st_cell_c),
            Paragraph(safe_str(it.get('texto', '')), st_norm),
            Paragraph(safe_str(it.get('und', '')), st_cell_c),
            Paragraph(fmt_num(cant), st_cell_r),
            Paragraph(fmt_soles(vu), st_cell_r),
            Paragraph(f'{fee:g}%', st_cell_c),
            Paragraph(fmt_soles(vt), st_cell_r),
            Paragraph(safe_str(it.get('comentarios', '')), st_norm),
        ])

    total_fee = sum(items_ok)
    it_rows.append([
        '', '', '', '', '', '',
        Paragraph('<b>sub total + FEE</b>', st_bold),
        Paragraph(f'<b>{fmt_soles(total_fee)}</b>', st_cell_r),
        '',
    ])

    n_it = len(it_rows)
    it_tbl = Table(it_rows, colWidths=it_cols, repeatRows=1)
    it_style = [
        ('BACKGROUND', (0, 0), (-1, 0), STEEL),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.4, MID_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, max(n_it - 2, 1)), [WHITE, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Fila total resaltada
        ('BACKGROUND', (0, n_it - 1), (-1, n_it - 1), YELLOW),
        ('SPAN', (0, n_it - 1), (5, n_it - 1)),
        ('ALIGN', (6, n_it - 1), (7, n_it - 1), 'RIGHT'),
    ]
    if not items_ok:
        it_style.append(('SPAN', (0, 1), (-1, 1)))
        it_rows.append([Paragraph('Sin items registrados.', st_norm), '', '', '', '', '', '', '', ''])
    it_tbl.setStyle(TableStyle(it_style))
    story.append(it_tbl)
    story.append(Spacer(1, 4 * mm))

    # ---- SECCIONES FIJAS DE CIERRE ----
    secciones_cierre = {
        'TIEMPO DE ENTREGA': '',
        'LUGAR DE ENTREGA': 'En la puerta del site',
        'VALIDEZ DE LA OFERTA': '15 días calendario',
        'CONDICIONES GENERALES': ''
    }
    for titulo, contenido in secciones_cierre.items():
        sec_tbl = Table([[Paragraph(f'<b>{titulo}</b>', st_sec)]], colWidths=[W])
        sec_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, MID_GRAY),
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(sec_tbl)
        if contenido:
            body_tbl = Table([[Paragraph(contenido, st_norm)]], colWidths=[W])
            body_tbl.setStyle(TableStyle([
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(body_tbl)
        story.append(Spacer(1, 1.5 * mm))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _obtener_registro_cotizacion():
    """Valida proyecto actual = Cotizaciones y devuelve el registro por key."""
    data = request.json or {}
    key_val = str(data.get('key', '')).strip()
    pid = session.get('current_proyecto_id')
    proy_obj = db.session.get(Proyecto, pid)
    if not key_val:
        return None, None, ({'error': 'Falta la clave del registro'}, 400)
    if not proy_obj or (proy_obj.nombre or '').strip().lower() != 'cotizaciones':
        return None, None, ({'error': 'Proyecto inválido'}, 400)
    rec = NucleusData.query.filter_by(proyecto_id=pid, key_value=key_val).first()
    if not rec:
        return None, None, ({'error': 'Cotización no encontrada'}, 404)
    return rec, proy_obj, None


def _cotizacion_registro_pdf_response(rec):
    """Construye el PDF Cobra desde un registro del módulo Cotizaciones.
    Solo si la cotización ya fue GENERADA (bloqueo respetado en todas las vías).
    Si NUMERO WO está vacío, muestra CM-PENDIENTE como en Combustible."""
    try:
        d = json.loads(rec.data_json)
    except Exception:
        d = {}
    if str(d.get('GENERADA', '') or '') != '1':
        return jsonify({'error': 'La cotización aún no ha sido generada. Usa "Generar Cotización" primero.'}), 400
    try:
        items = json.loads(d.get('ITEMS_JSON') or '[]')
    except Exception:
        items = []
    numero = str(d.get('N° COTIZACION', '') or '')
    # NUMERO WO → CM-PENDIENTE si está vacío, igual que Combustible
    numero_wo = str(d.get('NUMERO WO', '') or '').strip()
    ticket_raw = str(d.get('TICKET', '') or '').strip()
    # Para el PDF, el campo TICKET muestra el NUMERO WO asociado o CM-PENDIENTE
    pdf_ticket = numero_wo if numero_wo else "CM-PENDIENTE"
    pdf_bytes = _generar_pdf_cotizacion_cobra(
        numero=numero,
        site=str(d.get('SITE', '') or d.get('NOMBRE SITE', '') or ''),
        supervisor=str(d.get('SUPERVISOR', '') or ''),
        objetivo=str(d.get('OBJETIVO', '') or ''),
        ticket=pdf_ticket,
        elaborado_por=str(d.get('GESTOR', '') or session.get('username', '')),
        items=items
    )
    from flask import make_response
    resp = make_response(pdf_bytes)
    safe_num = numero.replace('/', '-').replace(' ', '_') or 'cotizacion'
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=Cotizacion_{safe_num}.pdf'
    return resp