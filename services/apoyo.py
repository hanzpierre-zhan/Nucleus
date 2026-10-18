# -*- coding: utf-8 -*-
"""services/apoyo.py
Almacenamiento de evidencia (disco local, Backblaze B2 y OneDrive).

La maquetacion del reporte PEXT vive en `services/pext_reporte.py` y los PDFs
de cotizacion en `services/cotizacion_pdf.py`; aqui se reexportan para no
romper a quien los importaba desde este modulo. Este archivo ya no contiene
rutas HTTP oficiales, pero conserva helpers historicos usados por blueprints.
"""
import glob
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app, session
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

from db import db
from models import Proyecto, TokenStore, NucleusData

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
    from services.sustento import bloqueado, registro_evidencia
    registro=registro_evidencia(pid,str(key or ''))
    if registro and bloqueado(json.loads(registro.data_json or '{}')):
        return True
    if registro and hasattr(registro,'cot') and bloqueado(json.loads(registro.cot.data_json or '{}')):
        return True

    if str(session.get('rol') or '').strip().lower() != 'contrata':
        return False
    proy = db.session.get(Proyecto, pid) if pid else None
    if not proy or (proy.nombre or '').strip() not in ('FLM', 'FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - CLARO', 'FLM - PEXT', 'FLM - CLARO y INTEGRATEL', 'PEXT'):
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

# ── Reexportes de compatibilidad ───────────────────────────────────────────
# Los blueprints/servicios importan estos nombres desde `services` (que a su vez
# los toma de aqui), asi que se mantienen disponibles aunque su implementacion
# viva ahora en otro modulo.
from services.pext_reporte import (  # noqa: E402
    EVIDENCIA_MAX_PEX, PEX_REPORTE_XLSX, PEX_SLOTS, PEX_ANCHORS, PEX_OBS_CELLS,
    _box_px, _n_a_en_box, _encajar_foto_cover,
    _pext_config, _pext_config_cajas, _pext_max,
)
from services.cotizacion_pdf import (  # noqa: E402
    _fecha_larga_es, _parse_fecha_registro,
    _generar_pdf_cotizacion, _generar_pdf_cotizacion_cobra,
    _obtener_registro_cotizacion, _cotizacion_registro_pdf_response,
)

__all__ = [
    'EVIDENCIA_TIPOS', 'EVIDENCIA_MAX_POR_TIPO', 'EVIDENCIA_MAX_PEX',
    'EVIDENCIA_TIPO_RESGUARDO', 'EVIDENCIA_MAX_RESGUARDO', 'EVIDENCIA_EXT_ALLOWED',
    'PEX_REPORTE_XLSX', 'PEX_SLOTS', 'PEX_ANCHORS', 'PEX_OBS_CELLS',
    'evidencia_folder', 'evidencia_limpiar_slot', 'evidencia_comprimir',
    'evidencia_usa_b2', 'b2_cliente', 'evidencia_eliminar_b2',
    'OD_GRAPH_BASE', 'OD_TOKEN_URL', '_od_cuenta', '_od_refresh_token_guardar',
    '_od_refresh_token_actual', 'onedrive_access_token', '_od_url',
    '_onedrive_subir_a', 'onedrive_subir', '_onedrive_eliminar_a', 'onedrive_eliminar',
    '_evidencia_aprobacion_bloquea', '_EVIDENCIA_OLD26_A_NUEVO',
    '_evidencia_migrar_legacy', '_evidencia_leer', '_box_px', '_n_a_en_box',
    '_encajar_foto_cover', '_pext_config', '_pext_config_cajas', '_pext_max',
    '_fecha_larga_es', '_parse_fecha_registro', '_generar_pdf_cotizacion',
    '_generar_pdf_cotizacion_cobra', '_obtener_registro_cotizacion',
    '_cotizacion_registro_pdf_response',
]
