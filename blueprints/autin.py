# -*- coding: utf-8 -*-
"""blueprints/autin.py
Pestana AUTIN: fotos de campo de un WO.

Lee las fotos desde (en orden de preferencia): un enlace compartido de
SharePoint, un servidor HTTP de fotos o la carpeta local de la PC. Se separo de
`blueprints/wo.py` porque este subsistema (~1000 lineas de listado remoto,
SharePoint y ZIP) no comparte estado con el resto de rutas WO; solo expone
`/api/autin/*`.
"""

import http.cookiejar
import io
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from flask import Blueprint, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

from db import db
from models import AppConfig, NucleusData, Proyecto
from services import get_session_info, login_required

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

bp = Blueprint('autin', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# AUTIN · fotos del WO leídas desde una PC/unidad montada
#   Estructura esperada:  <RAIZ>\<prefijo><WO NUMBER>\arrive_1.jpg ...
#   La RAIZ se resuelve:  env AUTIN_FOTOS_DIR  >  AppConfig(autin_fotos_dir)  >  <BASE>/fotos_autin
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata

AUTIN_CLAVE = 'autin_fotos_dir'
AUTIN_BASE_CLAVE = 'autin_fotos_base_url'   # URL del servidor de fotos de la PC (24/7)
AUTIN_TOKEN_CLAVE = 'autin_fotos_token'     # token opcional (?k=) del servidor de fotos
_AUTIN_IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic', '.avif')
_AUTIN_ESTADOS = ('llegada', 'completado', 'salida', 'suspendido', 'otros')
_AUTIN_LABEL = {'llegada': 'Llegada', 'completado': 'Completado', 'salida': 'Salida',
                'suspendido': 'Suspendido', 'otros': 'Otros'}
_AUTIN_ICONO = {'llegada': 'fa-location-dot', 'completado': 'fa-flag-checkered',
                'salida': 'fa-door-open', 'suspendido': 'fa-pause', 'otros': 'fa-images'}
_AUTIN_MAX_FOTOS = 500
_AUTIN_MAX_PROF = 3
_AUTIN_ZIP_MAX = 400 * 1024 * 1024  # tope del ZIP generado en memoria (400 MB)


def _autin_norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()


def _autin_estado(nombre):
    """Clasifica el archivo por el prefijo/palabra de estado en su nombre."""
    base = _autin_norm(os.path.splitext(str(nombre or ''))[0])
    if 'susp' in base or 'deten' in base:
        return 'suspendido'
    if 'arrive' in base or 'arrival' in base or 'llegad' in base or 'inicio' in base or 'entrad' in base:
        return 'llegada'
    if 'complete' in base or 'completad' in base or 'cierre' in base or 'finaliz' in base or 'terminad' in base:
        return 'completado'
    if 'leave' in base or 'leaving' in base or 'salida' in base or 'exit' in base:
        return 'salida'
    return 'otros'


def _autin_dentro(raiz, destino):
    try:
        return os.path.commonpath([raiz, destino]) == raiz
    except Exception:
        return False


def _autin_raiz(pid):
    """Raíz configurada: env > AppConfig(del proyecto del WO) > AppConfig(sesión) > carpeta por defecto."""
    p = (os.environ.get('AUTIN_FOTOS_DIR') or '').strip().strip('"')
    origen = 'env'
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
            origen = 'proyecto'
    if not p:
        cfg = AppConfig.query.filter_by(clave=AUTIN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
            origen = 'global'
    if not p:
        p = os.path.join(BASE_DIR, 'fotos_autin')
        origen = 'defecto'
    return p, origen


def _autin_base_url(pid):
    """URL pública del servidor de fotos (la PC que deja de estar 24/7).
       Vacío = se leen las fotos del disco local (modo actual)."""
    p = (os.environ.get('AUTIN_FOTOS_BASE_URL') or '').strip().strip('"').rstrip('/')
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_BASE_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip().rstrip('/')
    if not p:
        cfg = AppConfig.query.filter_by(clave=AUTIN_BASE_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip().rstrip('/')
    return p


def _autin_token(pid):
    """Token opcional que exige el servidor de fotos (?k=...)."""
    p = (os.environ.get('AUTIN_FOTOS_TOKEN') or '').strip()
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_TOKEN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
    if not p:
        cfg = AppConfig.query.filter_by(clave=AUTIN_TOKEN_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
    return p


def _autin_url(base, ruta, token='', qs=''):
    """Arma una URL del servidor de fotos: <base>/<ruta>[?k=...&qs]"""
    u = str(base or '').rstrip('/') + '/' + str(ruta or '').lstrip('/')
    pares = []
    if token:
        pares.append('k=' + urllib.parse.quote(str(token)))
    if qs:
        pares.append(str(qs))
    return u + (('?' + '&'.join(pares)) if pares else '')


def _autin_ping(base, token='', timeout=2.0):
    """¿Responde el servidor de fotos? (si la PC está apagada, False)."""
    try:
        req = urllib.request.Request(_autin_url(base, 'healthz', token),
                                     headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, 'status', 200) < 300
    except Exception:
        return False


def _autin_remota(base, token, wo, timeout=6.0):
    """Lee el listado de fotos del WO desde el servidor de la PC.
       Devuelve el dict del servidor o None si no responde."""
    try:
        qs = 'wo=' + urllib.parse.quote(str(wo))
        req = urllib.request.Request(_autin_url(base, 'api/fotos', token, qs),
                                     headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


_AUTIN_HREF_RE = re.compile(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
_AUTIN_PREFIJO_CACHE = {}   # (base, raiz) -> (ts, prefijo)


def _autin_enc(ruta):
    """Codifica cada segmento de una ruta relativa conservando los '/'."""
    return '/'.join(urllib.parse.quote(str(p)) for p in str(ruta or '').split('/'))


def _autin_http_get(url, timeout=8.0):
    """GET en texto plano. None si no responde o el estado no es 2xx."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= getattr(resp, 'status', 200) < 300):
                return None
            return resp.read().decode('utf-8', 'replace')
    except Exception:
        return None


def _autin_listado(url, timeout=8.0):
    """Lee un listado HTML de directorios (python -m http.server, nginx).
       Devuelve [(nombre, es_dir)] o None si la página no es un listado."""
    doc = _autin_http_get(url, timeout)
    if doc is None:
        return None
    baja = doc.lower()
    if 'directory listing for' not in baja and 'index of ' not in baja and \
       'parent directory' not in baja and '../' not in doc:
        return None
    entradas = []
    for href, _texto in _AUTIN_HREF_RE.findall(doc):
        h = href.strip()
        if not h or h.startswith(('#', '?', 'http://', 'https://')):
            continue
        nombre = urllib.parse.unquote(h).lstrip('/')
        if nombre.startswith('..') or '/' in nombre.rstrip('/'):
            continue
        nombre = nombre.rstrip('/')
        if nombre:
            entradas.append((nombre, h.endswith('/')))
    return entradas


def _autin_modo(base, token='', timeout=8.0):
    """Cómo entrega las fotos la URL guardada:
       'api' = servidor_api (con /healthz) · 'estatico' = python -m http.server · '' = sin servidor."""
    if not base:
        return ''
    if _autin_ping(base, token, timeout=2.5):
        return 'api'
    raices = _autin_listado(_autin_url(base, '', token), timeout)
    if raices and any(d for _n, d in raices):
        return 'estatico'
    return ''


def _autin_prefijo_estatico(base, raiz, token='', timeout=8.0):
    """Carpeta dentro del servidor que contiene la raíz de fotos ('' = ya es la raíz del servidor)."""
    clave = (base, str(raiz or ''))
    hit = _AUTIN_PREFIJO_CACHE.get(clave)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    valor = None
    nombre = os.path.basename(str(raiz or '').rstrip('\\/'))
    if nombre and _autin_listado(_autin_url(base, _autin_enc(nombre), token), timeout) is not None:
        valor = nombre
    elif _autin_listado(_autin_url(base, '', token), timeout) is not None:
        valor = ''
    if valor is not None:
        _AUTIN_PREFIJO_CACHE[clave] = (time.time(), valor)
    return valor


def _autin_carpeta_estatica(base, prefijo, wo, token='', timeout=8.0):
    """Carpeta del WO dentro del servidor (misma lógica que _autin_carpeta pero sobre el listado)."""
    wo_l = _autin_norm(wo)
    if not wo_l:
        return None
    ruta = _autin_enc(prefijo) + '/' if prefijo else ''
    entradas = _autin_listado(_autin_url(base, ruta, token), timeout)
    if entradas is None:
        return None
    carpetas = [n for n, d in entradas if d]
    for nivel in (0, 1, 2):
        for n in carpetas:
            nn = _autin_norm(n)
            if (nivel == 0 and nn == wo_l) or (nivel == 1 and nn.startswith(wo_l)) or \
               (nivel == 2 and wo_l in nn):
                return n
    return None


def _autin_listar_estatico(base, carpeta_rel, token='', timeout=8.0):
    """Imágenes del WO recorriendo los listados HTML (equivalente remoto de _autin_listar)."""
    encontrados = []
    pendientes = [(_autin_enc(carpeta_rel), '', 0)]
    while pendientes and len(encontrados) < _AUTIN_MAX_FOTOS:
        u, rel, prof = pendientes.pop(0)
        entradas = _autin_listado(_autin_url(base, u + '/', token), timeout)
        if entradas is None:
            continue
        for nombre, es_dir in entradas:
            if len(encontrados) >= _AUTIN_MAX_FOTOS:
                break
            if es_dir:
                if prof < _AUTIN_MAX_PROF:
                    pendientes.append((u + '/' + _autin_enc(nombre), rel + nombre + '/', prof + 1))
                continue
            if os.path.splitext(nombre)[1].lower() in _AUTIN_IMG_EXT:
                encontrados.append(rel + nombre)
    encontrados.sort(key=lambda s: s.lower())
    return encontrados


def _autin_remota_estatica(base, raiz, wo, token='', timeout=8.0):
    """Fotos del WO leídas de un servidor de archivos estático.
       Devuelve {'estado': 'ok'|'sin_carpeta'|'sin_servidor', ...}"""
    prefijo = _autin_prefijo_estatico(base, raiz, token, timeout)
    if prefijo is None:
        return {'estado': 'sin_servidor'}
    carpeta = _autin_carpeta_estatica(base, prefijo, wo, token, timeout)
    if not carpeta:
        return {'estado': 'sin_carpeta'}
    carpeta_rel = (prefijo + '/' + carpeta) if prefijo else carpeta
    return {'estado': 'ok', 'carpeta': carpeta, 'carpeta_rel': carpeta_rel,
            'rels': _autin_listar_estatico(base, carpeta_rel, token, timeout)}


def _autin_get_bytes(url, timeout=45.0):
    """Descarga binaria de un archivo del servidor remoto. None si no está."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Nucleus'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= getattr(resp, 'status', 200) < 300):
                return None
            return resp.read()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# AUTIN · fotos del WO en SharePoint / OneDrive por el enlace compartido
#   ("cualquiera con el enlace").  El enlace entrega una cookie FedAuth anónima;
#   con ella la carpeta se lee por REST desde cualquier servidor (Render incluido),
#   así que la PC dedicada deja de ser el único punto de falla.
# ─────────────────────────────────────────────────────────────────────────────
AUTIN_SP_CLAVE = 'autin_sp_link'      # enlace compartido de la carpeta de fotos
_AUTIN_SP_TTL = 1800.0                # la cookie FedAuth se renueva cada 30 min
_AUTIN_SP_REINTENTO = 60.0            # tras un fallo no se reintenta por 1 min
_AUTIN_SP_SES = {}                    # pid -> (ts, {api, raiz, opener})
_AUTIN_SP_FALLA = {}                  # pid -> ts del último fallo
_AUTIN_SP_CARPETAS = {}               # (pid, raiz, base) -> (ts, {normalizado: nombre})
_AUTIN_SP_WO = {}                     # (pid, wo) -> (ts, base, carpeta)
_AUTIN_SP_BASE = {}                   # (pid, raiz) -> (ts, base)
_AUTIN_SP_RELS = {}                   # (pid, wo) -> (ts, [fotos])
_AUTIN_SP_POOL = None


def _autin_sp_pool():
    """Hilos para preguntar a la vez archivos y subcarpetas (SharePoint tarda ~1s)."""
    global _AUTIN_SP_POOL
    if _AUTIN_SP_POOL is None:
        from concurrent.futures import ThreadPoolExecutor
        _AUTIN_SP_POOL = ThreadPoolExecutor(max_workers=4)
    return _AUTIN_SP_POOL


def _autin_es_enlace_sp(u):
    """¿Es esto un enlace compartido de SharePoint/OneDrive?"""
    u = str(u or '').lower()
    return ('sharepoint.com' in u or 'sharepoint.' in u or '1drv.ms' in u
            or 'onedrive.live' in u or 'my.sharepoint' in u)


def _autin_sp_link(pid):
    """Enlace compartido de la carpeta de fotos. Vacío = este modo está apagado.
       Vale en AUTIN_SP_LINK (env), en la fila autin_sp_link y también si el usuario
       lo pegó directamente en el campo de 'URL del servidor de fotos'."""
    p = (os.environ.get('AUTIN_SP_LINK') or '').strip().strip('"')
    if not p and pid:
        cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_SP_CLAVE).first()
        if cfg and (cfg.valor or '').strip():
            p = cfg.valor.strip()
    if not p:
        # último recurso: la config de otro proyecto de AUTIN (nunca de otro módulo,
        # para que un Rendición o Material no se meta a buscar fotos donde no hay)
        for nombre in ('FLM - ENTEL', 'FLM - INTEGRATEL', 'FLM - PEXT', 'FLM', 'PEXT'):
            pr = Proyecto.query.filter_by(nombre=nombre).first()
            if not pr:
                continue
            cfg = AppConfig.query.filter_by(proyecto_id=pr.id, clave=AUTIN_SP_CLAVE).first()
            if cfg and (cfg.valor or '').strip():
                p = cfg.valor.strip()
                break
    if not p:
        # si el usuario pegó el enlace en el campo de 'URL del servidor de fotos',
        # ahí vale igual (es donde siempre estaba el enlace a la PC/túnel)
        b = _autin_base_url(pid)
        if _autin_es_enlace_sp(b):
            p = b
    return p if re.match(r'^https?://', p) else ''


def _autin_sp_q(ruta):
    """Codifica una ruta de SharePoint para poder meterla dentro de la URL de la API."""
    return urllib.parse.quote(str(ruta or ''), safe="/'")


def _autin_sp_sesion(pid, timeout=15.0, forzar=False):
    """Sesión con SharePoint: recorre el enlace, guarda la cookie FedAuth y deduce
       dónde está el REST.  Devuelve el dict de sesión o None si no se pudo."""
    link = _autin_sp_link(pid)
    if not link:
        return None
    if not forzar:
        if time.time() - _AUTIN_SP_FALLA.get(pid, 0) < _AUTIN_SP_REINTENTO:
            return None
        hit = _AUTIN_SP_SES.get(pid)
        if hit and time.time() - hit[0] < _AUTIN_SP_TTL:
            return hit[1]
    try:
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req = urllib.request.Request(link, headers={'User-Agent': 'Nucleus'})
        with op.open(req, timeout=timeout) as resp:
            final = resp.geturl()
            resp.read(512)
        # el enlace cae en  onedrive.aspx?id=<carpeta>
        raiz = urllib.parse.parse_qs(urllib.parse.urlparse(final).query).get('id', [''])[0]
        if not raiz.startswith('/'):
            raise ValueError('el enlace no trajo la carpeta')
        sp = urllib.parse.urlparse(link)
        # el sitio web es lo que va antes de /Documents (OneDrive for Business)
        sitio = (os.environ.get('AUTIN_SP_SITE') or '').strip().rstrip('/')
        if not sitio:
            sitio = raiz.split('/Documents')[0] if '/Documents' in raiz else ''
        if not sitio:
            raise ValueError('no se pudo deducir el sitio de la coleccion')
        ses = {'api': '%s://%s%s/_api/web' % (sp.scheme, sp.netloc, sitio),
               'raiz': raiz.rstrip('/'), 'opener': op, 'link': link}
    except Exception:
        _AUTIN_SP_FALLA[pid] = time.time()
        return None
    _AUTIN_SP_SES[pid] = (time.time(), ses)
    _AUTIN_SP_FALLA.pop(pid, None)
    return ses


def _autin_sp_pedir(ses, url, timeout=15.0, params='', binario=False):
    """Petición con una sesión YA resuelta. No toca la BD, así que se puede usar
       desde un hilo (el contexto de Flask no se hereda a los hilos)."""
    u = url if str(url).startswith('http') else ses['api'] + url
    if params:
        u += ('&' if '?' in u else '?') + params
    headers = {'User-Agent': 'Nucleus',
               'Accept': 'application/octet-stream' if binario
               else 'application/json;odata=nometadata'}
    req = urllib.request.Request(u, headers=headers)
    with ses['opener'].open(req, timeout=timeout) as resp:
        crudo = resp.read()
    return crudo if binario else json.loads(crudo.decode('utf-8', 'replace'))


def _autin_sp_api(pid, url, timeout=15.0, params='', binario=False, reintentar=True):
    """Petición al REST de SharePoint usando la cookie de la sesión.
       Devuelve (ok, datos): datos es el dict JSON o los bytes del archivo."""
    ses = _autin_sp_sesion(pid, timeout=timeout)
    if not ses:
        return False, None
    try:
        return True, _autin_sp_pedir(ses, url, timeout, params, binario)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and reintentar:
            # cookie vencida: se recorre el enlace otra vez y se repite una vez
            _autin_sp_sesion(pid, timeout=timeout, forzar=True)
            return _autin_sp_api(pid, url, timeout, params, binario, False)
        return False, None
    except Exception:
        return False, None


def _autin_sp_ruta(ses, *partes):
    """Ruta de una subcarpeta/archivo dentro de la raíz de fotos."""
    limpio = [str(p).strip('/') for p in partes if p]
    return '/'.join([ses['raiz'].rstrip('/')] + limpio) if limpio else ses['raiz']


def _autin_sp_rel_ok(rel):
    """Valida un nombre relativo de foto: sin '../' ni rutas raras, y que sea imagen."""
    rel = str(rel or '').replace('\\', '/').strip('/')
    if not rel or os.path.splitext(rel)[1].lower() not in _AUTIN_IMG_EXT:
        return None
    for seg in rel.split('/'):
        if not seg or seg in ('.', '..'):
            return None
    return rel


def _autin_sp_base(pid, ses, timeout=15.0):
    """Carpeta que realmente contiene los WOs.  El enlace apunta a 'Evidencias', pero
       los WOs cuelgan de una subcarpeta que se llama como el proyecto ('FLM - ENTEL')."""
    clave = (pid, ses['raiz'])
    hit = _AUTIN_SP_BASE.get(clave)
    if hit and time.time() - hit[0] < _AUTIN_SP_TTL:
        return hit[1]
    try:
        nombre = (Proyecto.query.get(pid).nombre or '') if pid else ''
    except Exception:
        nombre = ''
    base = ''
    if nombre:
        ok, js = _autin_sp_api(pid, "/GetFolderByServerRelativeUrl('" +
                              _autin_sp_q(_autin_sp_ruta(ses, nombre)) + "')/Folders?$top=1", timeout)
        if ok and isinstance(js, dict) and js.get('value'):
            base = nombre
    _AUTIN_SP_BASE[clave] = (time.time(), base)
    return base


def _autin_sp_inventario(pid, ses, base, carpeta, timeout=15.0):
    """Fotos (rutas relativas) de la carpeta del WO, entrando a las subcarpetas.
       Devuelve (fotos, hay_algo): hay_algo False = esa carpeta no existe, porque
       SharePoint responde 200 con lista vacía en vez de 404."""
    fotos = []
    hay = False
    pendientes = [(carpeta, '', 0)]
    pool = _autin_sp_pool()
    while pendientes and len(fotos) < _AUTIN_MAX_FOTOS:
        actual, rel, prof = pendientes.pop(0)
        ruta = _autin_sp_ruta(ses, base, actual) if base else _autin_sp_ruta(ses, actual)
        url = "/GetFolderByServerRelativeUrl('" + _autin_sp_q(ruta) + "')"
        # archivos y subcarpetas van juntos: son dos viajes de ~1s cada uno
        fut_arch = pool.submit(_autin_sp_pedir, ses, url + '/Files', timeout, '$select=Name&$top=500')
        fut_car = (pool.submit(_autin_sp_pedir, ses, url + '/Folders', timeout, '$select=Name&$top=500')
                   if prof < _AUTIN_MAX_PROF else None)
        try:
            js = fut_arch.result()
        except Exception:
            js = None
        if isinstance(js, dict):
            for it in js.get('value') or []:
                n = str(it.get('Name') or '')
                if not n:
                    continue
                hay = True
                if os.path.splitext(n)[1].lower() in _AUTIN_IMG_EXT:
                    fotos.append(rel + n)
        if fut_car is not None:
            try:
                js2 = fut_car.result()
            except Exception:
                js2 = None
            if isinstance(js2, dict):
                for it in js2.get('value') or []:
                    n = str(it.get('Name') or '')
                    if not n or '/' in n or n in ('.', '..'):
                        continue
                    hay = True
                    pendientes.append(((actual + '/' + n) if actual else n, rel + n + '/', prof + 1))
    fotos.sort(key=lambda s: s.lower())
    return fotos, hay


def _autin_sp_mapa(pid, ses, base, timeout=25.0):
    """Mapa {normalizado: nombre} de las carpetas de 'base' (cache 30 min).

       IMPORTANTE: SharePoint NO emite @odata.nextLink en GetFolderByServerRelativeUrl
       (devuelve nextLink=None aunque queden más carpetas), así que con $top=500 se
       quedaba en 500 de 1530 y el respaldo por prefijo/contenido no encontraba la
       carpeta del WO ("Sin carpeta de fotos para este WO."). Se pide de una sola
       vez con $top=5000 y, si acaso viniera paginado, se sigue tanto @odata como
       odata.nextLink."""
    clave = (pid, ses['raiz'], base)
    hit = _AUTIN_SP_CARPETAS.get(clave)
    if hit and time.time() - hit[0] < _AUTIN_SP_TTL:
        return hit[1]
    mapa = {}
    raiz = _autin_sp_ruta(ses, base) if base else ses['raiz']
    url = ("/GetFolderByServerRelativeUrl('" + _autin_sp_q(raiz) + "')/Folders?$select=Name&$top=5000")
    while url and len(mapa) < 20000:
        ok, js = _autin_sp_api(pid, url, timeout)
        if not ok or not isinstance(js, dict):
            break
        for it in js.get('value') or []:
            n = str(it.get('Name') or '')
            if n:
                mapa.setdefault(_autin_norm(n), n)
        url = str(js.get('@odata.nextLink') or js.get('odata.nextLink') or '')
    _AUTIN_SP_CARPETAS[clave] = (time.time(), mapa)
    return mapa


def _autin_sp_bytes(pid, ses, base, carpeta, rel, timeout=45.0):
    """Descarga una foto desde SharePoint. None si no se pudo."""
    rel = _autin_sp_rel_ok(rel)
    if not rel:
        return None
    ruta = _autin_sp_ruta(ses, base, carpeta, rel) if base else _autin_sp_ruta(ses, carpeta, rel)
    u = "/GetFileByServerRelativeUrl('" + _autin_sp_q(ruta) + "')/$value"
    ok, data = _autin_sp_api(pid, u, timeout, binario=True)
    return data if ok and data else None


def _autin_sp_wo(pid, wo, timeout=15.0):
    """Fotos del WO desde SharePoint.
       {'estado': 'ok'|'sin_carpeta'|'sin_servidor', 'carpeta', 'base', 'rels'}"""
    if not _autin_sp_link(pid):
        return {'estado': 'sin_servidor'}
    wo_l = _autin_norm(wo)
    if not wo_l:
        return {'estado': 'sin_carpeta'}
    ses = _autin_sp_sesion(pid, timeout=timeout)
    if not ses:
        return {'estado': 'sin_servidor'}
    base = _autin_sp_base(pid, ses, timeout)
    clave = (pid, _autin_norm(wo))
    hit = _AUTIN_SP_RELS.get(clave)
    if hit and time.time() - hit[0] < 300:
        return {'estado': 'ok', 'carpeta': wo, 'base': base, 'rels': hit[1]}
    fotos, hay = _autin_sp_inventario(pid, ses, base, wo, timeout)
    if not hay:
        # el nombre exacto no existe: se busca por prefijo o por contenido
        mapa = _autin_sp_mapa(pid, ses, base, timeout)
        for nivel in (1, 2):
            for nn, real in sorted(mapa.items()):
                if (nivel == 1 and nn.startswith(wo_l)) or (nivel == 2 and wo_l in nn):
                    fotos2, hay2 = _autin_sp_inventario(pid, ses, base, real, timeout)
                    if hay2:
                        _AUTIN_SP_RELS[(pid, _autin_norm(real))] = (time.time(), fotos2)
                        return {'estado': 'ok', 'carpeta': real, 'base': base, 'rels': fotos2}
    if not hay:
        return {'estado': 'sin_carpeta'}
    _AUTIN_SP_RELS[clave] = (time.time(), fotos)
    return {'estado': 'ok', 'carpeta': wo, 'base': base, 'rels': fotos}


def _autin_sp_ubicar(pid, wo, timeout=15.0):
    """(base, carpeta) del WO en SharePoint. Se cachea 10 min para no repetir el
       listado cada vez que se pide una foto suelta."""
    clave = (pid, _autin_norm(wo))
    hit = _AUTIN_SP_WO.get(clave)
    if hit and time.time() - hit[0] < 600:
        return hit[1], hit[2]
    info = _autin_sp_wo(pid, wo, timeout)
    if info.get('estado') != 'ok':
        return None, None
    base, carpeta = (info.get('base') or '', info['carpeta'])
    _AUTIN_SP_WO[clave] = (time.time(), base, carpeta)
    return base, carpeta


def _autin_sp_foto(pid, wo, rel, timeout=45.0):
    """Descarga una foto del WO desde SharePoint (None si no se pudo)."""
    rel = _autin_sp_rel_ok(rel)
    if not rel:
        return None
    base, carpeta = _autin_sp_ubicar(pid, wo, timeout)
    ses = _autin_sp_sesion(pid, timeout=timeout)
    if not ses or not carpeta:
        return None
    return _autin_sp_bytes(pid, ses, base, carpeta, rel, timeout)


def _autin_sp_responde(pid, wo, base):
    """Si el modo SharePoint está activo, llena 'base' con las fotos y devuelve True."""
    info = _autin_sp_wo(pid, wo)
    if info.get('estado') not in ('ok', 'sin_carpeta'):
        return False
    base['modo'] = 'sharepoint'
    # se devuelve el enlace que está en uso para que zeno lo vea y lo cambie
    # (si lo pegó en el campo de 'URL del servidor de fotos' también sirve)
    base['base_url'] = _autin_sp_link(pid)
    base['fotos_base'] = ''  # vacío = el front pide cada foto a /api/autin/foto
    base['zip_url'] = ''
    base['raiz_existe'] = True
    base['sin_conexion'] = False
    if info.get('estado') == 'sin_carpeta':
        base['mensaje'] = ('Sin carpeta de fotos para este WO: falta subir "%s" '
                           'a SharePoint (Evidencias\\FLM - ENTEL).' % wo)
        return True
    base['carpeta'] = info['carpeta']
    for rel in info['rels']:
        base['grupos'][_autin_estado(rel)].append(rel)
    base['total'] = sum(len(v) for v in base['grupos'].values())
    if not base['total']:
        base['mensaje'] = 'La carpeta del WO no contiene imágenes.'
    return True


def _autin_proyecto_del_wo(wo):
    for nombre in ('FLM - ENTEL', 'FLM', 'PEXT'):
        proy = Proyecto.query.filter_by(nombre=nombre).first()
        if not proy:
            continue
        if NucleusData.query.filter_by(proyecto_id=proy.id, key_value=wo).first():
            return proy.id
    return None


def _autin_carpeta(raiz, wo):
    """Carpeta del WO dentro de la raíz (nombre exacto, que empiece por el WO o que lo contenga)."""
    wo_l = _autin_norm(wo)
    if not wo_l or not os.path.isdir(raiz):
        return None
    try:
        nombres = sorted(os.listdir(raiz))
    except OSError:
        return None
    carpetas = [n for n in nombres if os.path.isdir(os.path.join(raiz, n))]
    for nivel in (0, 1, 2):  # exacto → prefijo → contiene
        for n in carpetas:
            nn = _autin_norm(n)
            if (nivel == 0 and nn == wo_l) or (nivel == 1 and nn.startswith(wo_l)) or \
               (nivel == 2 and wo_l in nn):
                return os.path.realpath(os.path.join(raiz, n))
    return None


def _autin_listar(carpeta):
    """Devuelve los archivos de imagen de la carpeta del WO (con subcarpetas, profundidad limitada)."""
    raiz_r = os.path.realpath(carpeta)
    encontrados = []
    pendientes = [(raiz_r, 0)]
    while pendientes and len(encontrados) < _AUTIN_MAX_FOTOS:
        actual, prof = pendientes.pop(0)
        try:
            entradas = sorted(os.listdir(actual))
        except OSError:
            continue
        for nombre in entradas:
            if len(encontrados) >= _AUTIN_MAX_FOTOS:
                break
            full = os.path.join(actual, nombre)
            try:
                es_dir = os.path.isdir(full)
            except OSError:
                continue
            if es_dir:
                if prof < _AUTIN_MAX_PROF:
                    pendientes.append((full, prof + 1))
                continue
            if os.path.splitext(nombre)[1].lower() in _AUTIN_IMG_EXT:
                encontrados.append(os.path.relpath(full, raiz_r).replace(os.sep, '/'))
    encontrados.sort(key=lambda s: s.lower())
    return encontrados


@bp.route('/api/autin/fotos', methods=['GET'])
@login_required
def api_autin_fotos():
    """Agrupa las fotos del WO por estado (llegada/completado/salida/suspendido)."""
    wo = (request.args.get('wo') or request.args.get('key') or '').strip()
    user_id, user_rol, pid_sesion = get_session_info()
    pid = _autin_proyecto_del_wo(wo) or pid_sesion
    if not wo:
        return jsonify({'success': False, 'error': 'Falta el número de WO'}), 400
    raiz, origen = _autin_raiz(pid)
    base_url = _autin_base_url(pid)
    token = _autin_token(pid)
    es_admin = user_rol in ('zeno', 'suport')
    base = {'success': True, 'wo': wo, 'raiz': raiz if es_admin else '', 'origen': origen if es_admin else '',
            'raiz_existe': os.path.isdir(raiz), 'carpeta': None, 'total': 0,
            'base_url': base_url if user_rol == 'zeno' else '',
            'modo': 'local' if not base_url else '', 'fotos_base': '', 'fotos_qs': '',
            'zip_url': '',
            'grupos': {e: [] for e in _AUTIN_ESTADOS}}

    # ── SharePoint: si hay enlace configurado, es la fuente de las fotos ──────
    # (no hay PC que prender ni unidad montada: se leen de la carpeta compartida)
    if _autin_sp_link(pid) and _autin_sp_responde(pid, wo, base):
        return jsonify(base)

    # Si hay enlace pero no respondió, se para aquí: el enlace NO es un servidor
    # de fotos, así que probarlo abajo solo daría el aviso engañoso de "PC apagada".
    if _autin_sp_link(pid):
        base['modo'] = 'sharepoint'
        base['base_url'] = _autin_sp_link(pid)
        base['fotos_base'] = ''
        base['raiz_existe'] = False
        base['sin_conexion'] = True
        base['mensaje'] = ('No se pudo leer el enlace compartido de SharePoint: '
                           'revisa que el enlace siga vigente y que la carpeta '
                           'comparta lectura pública.')
        return jsonify(base)

    # ── Modo servidor: las fotos viven en la PC 24/7, se piden a su URL ──────
    # (la 'raiz' local se conserva igual: es el respaldo si se vacía la URL)
    if base_url:
        qs = ('?k=' + urllib.parse.quote(token)) if token else ''
        modo = _autin_modo(base_url, token)
        base['modo'] = modo

        if modo == 'api':  # servidor_api (/healthz + /api/fotos + /zip)
            base['fotos_base'] = base_url + '/f/' + urllib.parse.quote(wo)
            base['fotos_qs'] = qs
            base['zip_url'] = _autin_url(base_url, 'zip', token, 'wo=' + urllib.parse.quote(wo))
            info = _autin_remota(base_url, token, wo)
            if info is None:
                base['modo'] = ''
                base['raiz_existe'] = False
                base['sin_conexion'] = True
                base['mensaje'] = 'Servidor de fotos no disponible (la PC está apagada o sin internet).'
                return jsonify(base)
            base['raiz_existe'] = True
            base['sin_conexion'] = False
            base['carpeta'] = info.get('carpeta') or None
            base['grupos'] = info.get('grupos') or {e: [] for e in _AUTIN_ESTADOS}
            base['total'] = info.get('total') or sum(len(v) for v in base['grupos'].values())
            base['mensaje'] = info.get('mensaje') or ''
            return jsonify(base)

        if modo == 'estatico':  # python -m http.server (listados de directorio)
            info = _autin_remota_estatica(base_url, raiz, wo, token)
            if info.get('estado') == 'ok':
                base['raiz_existe'] = True
                base['sin_conexion'] = False
                base['carpeta'] = info.get('carpeta')
                base['fotos_base'] = base_url + '/' + _autin_enc(info['carpeta_rel'])
                base['fotos_qs'] = qs
                for rel in info.get('rels') or []:
                    base['grupos'][_autin_estado(rel)].append(rel)
                base['total'] = sum(len(v) for v in base['grupos'].values())
                if not base['total']:
                    base['mensaje'] = 'La carpeta del WO no contiene imágenes.'
                return jsonify(base)
            if info.get('estado') == 'sin_carpeta':
                base['raiz_existe'] = True
                base['sin_conexion'] = False
                base['mensaje'] = 'Sin carpeta de fotos para este WO.'
                return jsonify(base)

        # (si hay enlace de SharePoint ya se cortó arriba: aquí solo hay servidor de PC)
        base['modo'] = ''
        base['raiz_existe'] = False
        base['sin_conexion'] = True
        base['mensaje'] = 'Servidor de fotos no disponible (la PC está apagada o sin internet).'
        return jsonify(base)

    if not base['raiz_existe']:
        base['mensaje'] = 'No se encuentra la carpeta de fotos Autin.'
        return jsonify(base)
    carpeta = _autin_carpeta(raiz, wo)
    if not carpeta:
        base['mensaje'] = 'Sin carpeta de fotos para este WO.'
        return jsonify(base)
    base['carpeta'] = os.path.basename(carpeta)
    raiz_r = os.path.realpath(raiz)
    for rel in _autin_listar(carpeta):
        if not _autin_dentro(raiz_r, os.path.realpath(os.path.join(carpeta, rel))):
            continue
        base['grupos'][_autin_estado(rel)].append(rel)
    base['total'] = sum(len(v) for v in base['grupos'].values())
    if not base['total']:
        base['mensaje'] = 'La carpeta del WO no contiene imágenes.'
    return jsonify(base)


@bp.route('/api/autin/foto', methods=['GET'])
@login_required
def api_autin_foto():
    """Sirve una foto del WO validando que quede dentro de la raíz configurada."""
    wo = (request.args.get('wo') or '').strip()
    rel = (request.args.get('f') or request.args.get('file') or '').strip()
    _, _, pid_sesion = get_session_info()
    pid = _autin_proyecto_del_wo(wo) or pid_sesion
    if not wo or not rel:
        abort(400)
    raiz, _ = _autin_raiz(pid)
    raiz_r = os.path.realpath(raiz)
    # SharePoint manda cuando está configurado: las fotos no están en el disco del
    # servidor (en Render no hay nada montado), se leen de la carpeta compartida.
    if _autin_sp_link(pid):
        data = _autin_sp_foto(pid, wo, rel)
        if data:
            resp = Response(data, mimetype=mimetypes.guess_type(rel)[0] or 'image/jpeg')
            resp.headers['Cache-Control'] = 'private, max-age=3600'
            return resp
    if not os.path.isdir(raiz_r):
        abort(404)
    carpeta = _autin_carpeta(raiz_r, wo) or raiz_r
    candidatos = [os.path.join(carpeta, rel), os.path.join(raiz_r, rel)]
    for cand in candidatos:
        full = os.path.realpath(cand)
        if not _autin_dentro(raiz_r, full):
            continue
        if os.path.isfile(full) and os.path.splitext(full)[1].lower() in _AUTIN_IMG_EXT:
            resp = send_file(full, conditional=True)
            resp.headers['Cache-Control'] = 'private, max-age=3600'
            return resp
    abort(404)


@bp.route('/api/autin/zip', methods=['GET'])
@login_required
def api_autin_zip():
    """ZIP con todas las fotos del WO (misma validación de raíz que /api/autin/foto)."""
    wo = (request.args.get('wo') or '').strip()
    if not wo:
        return jsonify({'error': 'Falta el número de WO'}), 400
    _, _, pid_sesion = get_session_info()
    pid = _autin_proyecto_del_wo(wo) or pid_sesion

    # ── SharePoint: es la fuente configurada, se atiende antes que la PC ──────
    if _autin_sp_link(pid):
        info = _autin_sp_wo(pid, wo)
        if info.get('estado') != 'ok':
            return jsonify({'error': 'Sin carpeta de fotos para este WO.'}), 404
        rels = info.get('rels') or []
        if not rels:
            return jsonify({'error': 'La carpeta del WO no contiene imágenes.'}), 404
        buf = io.BytesIO()
        total = 0
        count = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            for rel in rels:
                data = _autin_sp_foto(pid, wo, rel)
                if not data:
                    continue
                total += len(data)
                if total > _AUTIN_ZIP_MAX:
                    return jsonify({'error': 'Las fotos superan el límite de descarga (400 MB).'}), 413
                zf.writestr(rel, data)
                count += 1
        if not count:
            return jsonify({'error': 'No se pudieron descargar las fotos de SharePoint.'}), 502
        buf.seek(0)
        nombre = secure_filename(str(wo)) or 'wo'
        return send_file(buf, mimetype='application/zip', as_attachment=True,
                         download_name='autin_%s.zip' % nombre)

    base_url = _autin_base_url(pid)
    if base_url:
        token = _autin_token(pid)
        modo = _autin_modo(base_url, token)
        if modo == 'api':
            # Las fotos están en la PC remota: el ZIP lo genera su servidor.
            return jsonify({'error': 'Las fotos están en el servidor remoto.',
                            'zip_url': _autin_url(base_url, 'zip', token,
                                                  'wo=' + urllib.parse.quote(wo))}), 409
        if modo != 'estatico':
            return jsonify({'error': 'Servidor de fotos no disponible.'}), 503
        # Servidor de archivos estático (sin /zip): Render baja las fotos y arma el ZIP.
        raiz, _ = _autin_raiz(pid)
        info = _autin_remota_estatica(base_url, raiz, wo, token)
        if info.get('estado') != 'ok':
            return jsonify({'error': 'No se encontraron las fotos de este WO en el servidor.'}), 404
        qs = ('?k=' + urllib.parse.quote(token)) if token else ''
        fotos_base = base_url + '/' + _autin_enc(info['carpeta_rel'])
        buf = io.BytesIO()
        total = 0
        count = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            for rel in info.get('rels') or []:
                data = _autin_get_bytes(fotos_base + '/' + _autin_enc(rel) + qs)
                if not data:
                    continue
                total += len(data)
                if total > _AUTIN_ZIP_MAX:
                    return jsonify({'error': 'Las fotos superan el límite de descarga (400 MB).'}), 413
                zf.writestr(rel, data)
                count += 1
        if not count:
            return jsonify({'error': 'La carpeta del WO no contiene imágenes.'}), 404
        buf.seek(0)
        nombre = secure_filename(str(wo)) or 'wo'
        return send_file(buf, mimetype='application/zip', as_attachment=True,
                         download_name='autin_%s.zip' % nombre)

    raiz, _ = _autin_raiz(pid)
    if not os.path.isdir(raiz):
        return jsonify({'error': 'No se encuentra la carpeta de fotos Autin.'}), 404
    carpeta = _autin_carpeta(raiz, wo)
    if not carpeta:
        return jsonify({'error': 'Sin carpeta de fotos para este WO.'}), 404
    raiz_r = os.path.realpath(raiz)
    buf = io.BytesIO()
    total = 0
    count = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
        for rel in _autin_listar(carpeta):
            full = os.path.realpath(os.path.join(carpeta, rel))
            if not _autin_dentro(raiz_r, full) or not os.path.isfile(full):
                continue
            try:
                total += os.path.getsize(full)
                if total > _AUTIN_ZIP_MAX:
                    return jsonify({'error': 'Las fotos superan el límite de descarga (400 MB).'}), 413
                zf.write(full, rel)
                count += 1
            except OSError:
                continue
    if not count:
        return jsonify({'error': 'La carpeta del WO no contiene imágenes.'}), 404
    buf.seek(0)
    nombre = secure_filename(str(wo)) or 'wo'
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='autin_%s.zip' % nombre)


@bp.route('/api/autin/config', methods=['GET', 'POST'])
@login_required
def api_autin_config():
    """Consulta/guarda la raíz de fotos AUTIN (ruta: zeno/suport · URL del servidor: solo zeno).
       El guardado se hace sobre el proyecto del WO (todo el módulo), no por sesión."""
    user_id, user_rol, pid_sesion = get_session_info()
    es_admin = user_rol in ('zeno', 'suport')

    if request.method == 'POST':
        if not es_admin:
            return jsonify({'success': False, 'error': 'Sin permisos'}), 403
        form = request.form
        js = request.get_json(silent=True) or {}

        def _campo(k):
            if k in form:
                return form.get(k, '')
            if k in js:
                return js.get(k) or ''
            return None   # no se envió: no se modifica

        ruta = _campo('ruta')
        base_enviada = _campo('base_url')
        sp_enviado = _campo('sp_link')
        wo = (_campo('wo') or '').strip()

        if base_enviada is not None and user_rol != 'zeno':
            return jsonify({'success': False,
                            'error': 'La URL del servidor de fotos solo puede cambiarla zeno.'}), 403
        if sp_enviado is not None and user_rol != 'zeno':
            return jsonify({'success': False,
                            'error': 'El enlace de SharePoint solo puede cambiarlo zeno.'}), 403

        sp_link = None
        if sp_enviado is not None:
            sp_link = str(sp_enviado).strip()
            if sp_link and not re.match(r'^https?://', sp_link):
                return jsonify({'success': False,
                                'error': 'El enlace de SharePoint debe empezar con http:// o https://'}), 400

        base_url = None
        if base_enviada is not None:
            base_url = str(base_enviada).strip().rstrip('/')
            if base_url and not re.match(r'^https?://', base_url):
                return jsonify({'success': False,
                                'error': 'La URL del servidor debe empezar con http:// o https://'}), 400
        if ruta is None and base_url is None and sp_link is None:
            return jsonify({'success': False, 'error': 'Nada que guardar.'}), 400

        pid = _autin_proyecto_del_wo(wo) or pid_sesion
        if not pid:
            return jsonify({'success': False, 'error': 'Sin proyecto activo'}), 400

        if ruta is not None:
            cfg = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_CLAVE).first()
            if cfg:
                cfg.valor = str(ruta).strip()
            else:
                db.session.add(AppConfig(proyecto_id=pid, clave=AUTIN_CLAVE, valor=str(ruta).strip()))
        if base_enviada is not None:
            cfgb = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_BASE_CLAVE).first()
            if cfgb:
                cfgb.valor = base_url
            else:
                db.session.add(AppConfig(proyecto_id=pid, clave=AUTIN_BASE_CLAVE, valor=base_url))
        if sp_link is not None:
            cfgs = AppConfig.query.filter_by(proyecto_id=pid, clave=AUTIN_SP_CLAVE).first()
            if cfgs:
                cfgs.valor = sp_link
            else:
                db.session.add(AppConfig(proyecto_id=pid, clave=AUTIN_SP_CLAVE, valor=sp_link))
            # el enlace cambió: se cae la sesión/cache para no seguir con la vieja
            _AUTIN_SP_SES.pop(pid, None)
            _AUTIN_SP_CARPETAS.clear()
        db.session.commit()

    pid = pid_sesion
    raiz, origen = _autin_raiz(pid)
    base_url = _autin_base_url(pid)
    sp_link = _autin_sp_link(pid)
    return jsonify({'success': True, 'raiz': raiz if es_admin else '', 'origen': origen if es_admin else '',
                    'base_url': base_url if user_rol == 'zeno' else '',
                    'sp_link': sp_link if user_rol == 'zeno' else '',
                    'sp_activo': bool(sp_link),
                    'existe': os.path.isdir(raiz) or bool(base_url) or bool(sp_link),
                    'editable': es_admin})

