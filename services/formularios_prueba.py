"""Portal de técnicos: lectura del maestro y escritura exclusivamente en el piloto.

No inserta usuarios ni modifica nucleus_data, estados, integraciones o B2.
"""
import hashlib
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.client import HTTPException, HTTPSConnection
from pathlib import Path

from flask import current_app
from sqlalchemy import JSON, cast, func, select

from db import db
from models import NucleusData, Proyecto
from services.rendicion_estados import estado_de, etapa_de


def documento(value):
    return re.sub(r'[\s.\-]', '', str(value or '')).upper()


def valor(data, *keys):
    names = {str(k).strip().casefold(): v for k, v in data.items()}
    return next((names[k.casefold()] for k in keys if names.get(k.casefold()) not in (None, '')), '')


def raiz():
    return Path(current_app.config.get('FORM_PRUEBAS_DIR') or
                Path(current_app.instance_path) / 'formularios_prueba')


def consultar_ruc_externo(host, recurso, campo_nombre, campo_estado):
    conexion = HTTPSConnection(host, timeout=2.5)
    try:
        conexion.request('GET', recurso, headers={'Accept': 'application/json'})
        respuesta = conexion.getresponse()
        if respuesta.status != 200:
            return None
        datos = json.loads(respuesta.read(65536))
        if not isinstance(datos, dict):
            return None
        nombre, estado = datos.get(campo_nombre), datos.get(campo_estado)
        if isinstance(nombre, str) and nombre.strip() and isinstance(estado, str) and estado.strip():
            return {'resultado': 'encontrado', 'razon_social': nombre.strip(),
                    'activo': estado.strip().upper() == 'ACTIVO'}
    except (OSError, HTTPException, ValueError):
        return None
    finally:
        conexion.close()


def consultar_ruc(numero):
    if numero.startswith('20'):
        resultado = consultar_ruc_externo('openruc.com', f'/api/ruc/{numero}', 'razon_social', 'estado')
        if resultado:
            return resultado
    elif numero.startswith('10'):
        resultado = consultar_ruc_externo('ruc.kembec.com', f'/api/search/{numero}',
                                         'nombre-o-razon-social', 'estado-del-contribuyente')
        if resultado:
            return resultado
    return consultar_ruc_padron(numero)


def consultar_ruc_padron(numero):
    ruta = raiz() / 'padron-ruc.sqlite3'
    if not ruta.is_file():
        return {'resultado': 'no_disponible'}
    con = sqlite3.connect(ruta.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        fila = con.execute('SELECT razon_social, estado FROM ruc WHERE numero=?', (numero,)).fetchone()
    finally:
        con.close()
    if fila is None:
        return {'resultado': 'no_encontrado'}
    return {'resultado': 'encontrado', 'razon_social': fila['razon_social'],
            'activo': fila['estado'].strip().upper() == 'ACTIVO'}


@contextmanager
def almacen():
    folder = raiz()
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(folder / 'piloto.sqlite3'), timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.executescript('''
            CREATE TABLE IF NOT EXISTS envios (
                id TEXT PRIMARY KEY, documento TEXT NOT NULL, tipo TEXT NOT NULL,
                creado TEXT NOT NULL, datos TEXT NOT NULL, nonce TEXT NOT NULL,
                UNIQUE(documento, nonce));
            CREATE INDEX IF NOT EXISTS envios_documento ON envios(documento, tipo);
            CREATE TABLE IF NOT EXISTS intentos (
                clave TEXT PRIMARY KEY, cantidad INTEGER NOT NULL, inicio REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS huellas_comprobante (huella TEXT PRIMARY KEY);
        ''')
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def buscar_personal(doc):
    """Busca por clave DOCUMENTO sin cargar ni exponer el catálogo completo."""
    table = NucleusData.__table__
    rows = db.session.execute(select(table.c.id, table.c.data_json).join(
        Proyecto.__table__, table.c.proyecto_id == Proyecto.id).where(
            Proyecto.nombre == 'Dataper', table.c.key_value == doc)).all()
    candidates = []
    for row in rows:
        data = json.loads(row.data_json or '{}')
        if documento(valor(data, 'DOCUMENTO')) != doc:
            continue
        if str(valor(data, 'ESTADO')).strip().upper() != 'ACTIVO':
            continue
        name = str(valor(data, 'TECNICO')).strip()
        if name:
            candidates.append({'id': row.id, 'documento': doc, 'nombre': name,
                               'proyecto': str(valor(data, 'PROYECTO')).strip(),
                               'departamento': str(valor(data, 'DEPARTAMENTO')).strip(),
                               'supervisor': str(valor(data, 'SUPERVISOR')).strip()})
    # Un documento compartido por personas distintas no puede dar acceso.
    if len(candidates) != 1:
        return None
    return candidates[0]


def importe(value, *, permitir_cero=False):
    text = str(value or '').strip().replace('S/', '').replace(' ', '')
    if ',' in text and '.' not in text:
        text = text.replace(',', '.')
    else:
        text = text.replace(',', '')
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise ValueError('Escribe un monto válido, por ejemplo 25.50.') from None
    if not result.is_finite() or result < 0 or (not permitir_cero and result == 0) or result > 100000:
        raise ValueError('El monto debe ser mayor que cero y no superar S/ 100,000.')
    if result.as_tuple().exponent < -2:
        raise ValueError('El monto admite como máximo dos decimales.')
    return result.quantize(Decimal('.01'))


def _referencia(doc, code):
    return hmac.new(str(current_app.secret_key).encode(),
                    (doc + ':' + code).encode(), hashlib.sha256).hexdigest()


def filas_rendicion(doc, registro=None):
    table = NucleusData.__table__
    # Comparación por documento en SQL: nunca enviar depósitos ajenos al cliente.
    if db.engine.dialect.name == 'sqlite':
        extract = lambda key: func.json_extract(table.c.data_json, '$."' + key + '"')
    else:
        extract = lambda key: cast(table.c.data_json, JSON)[key].as_string()
    owner = func.coalesce(func.nullif(extract('Documento del beneficiario'), ''),
                          func.nullif(extract('Documento del beneficiario (Form)'), ''),
                          func.nullif(extract('DOCUMENTO'), ''), extract('DNI'), '')
    owner = func.upper(func.replace(func.replace(func.replace(func.trim(owner), ' ', ''), '.', ''), '-', ''))
    consulta = select(table.c.id, table.c.proyecto_id, table.c.key_value, table.c.data_json).join(
        Proyecto.__table__, table.c.proyecto_id == Proyecto.id).where(
            Proyecto.nombre == 'Rendicion', owner == doc)
    if registro is not None:
        consulta = consulta.where(table.c.id == registro)
    return db.session.execute(consulta.order_by(table.c.id.desc())).all()


def codigo_solicitud(uid):
    return 'PRUEBA-' + uid.upper()


def fecha_solicitud(valor_fecha):
    """Normaliza horas del formulario de Perú y registros ISO del piloto."""
    texto = str(valor_fecha or '').strip()
    if not texto:
        return ''
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
            try:
                fecha = datetime.strptime(texto, formato)
                break
            except ValueError:
                continue
        else:
            return ''
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone(timedelta(hours=-5)))
    return fecha.astimezone(timezone.utc).isoformat()


def partidas_guardadas(datos):
    if datos.get('partidas'):
        return datos['partidas']
    gastos = valor(datos, 'tipo_gasto', 'Tipo de gasto')
    if isinstance(gastos, str):
        gastos = re.split(r'[,;\n]+', gastos)
    if not isinstance(gastos, list):
        return []
    detalles = datos.get('detalle_gasto') or {}
    return [
        {'categoria': categoria, 'detalle': detalle}
        for categoria in dict.fromkeys(gasto.strip().upper() for gasto in gastos if isinstance(gasto, str) and gasto.strip())
        for detalle in detalles.get(categoria, [''])
    ]


def depositos(doc, filas=None):
    grouped = {}
    for row in filas if filas is not None else filas_rendicion(doc):
        data = json.loads(row.data_json or '{}')
        if estado_de(data) in ('RECHAZADO', 'ANULADO') or etapa_de(data) not in ('EVIDENCIA', 'OBSERVADO'):
            continue
        code = str(valor(data, 'CODIGO DEPOSITO')).strip()
        if not code:
            continue
        raw = valor(data, 'MONTO PAGO', 'Monto total del depósito', 'Monto', 'Monto total')
        try:
            amount = importe(raw)
        except ValueError:
            continue
        ref = _referencia(doc, code)
        solicitada = fecha_solicitud(valor(data, 'Marca temporal'))
        item = grouped.setdefault(ref, {'referencia': ref, 'codigo': code,
                                       'monto': Decimal('0'), 'pendiente': Decimal('0'),
                                       'motivo': str(valor(data, 'Motivo de la solicitud'))[:180],
                                       'partidas': [],
                                       'estado': 'Observado' if etapa_de(data) == 'OBSERVADO' else estado_de(data).capitalize(),
                                       'fecha_solicitud': solicitada,
                                       'fecha': str(valor(data, 'FECHA PAGO'))[:10]})
        if solicitada and (not item['fecha_solicitud'] or solicitada < item['fecha_solicitud']):
            item['fecha_solicitud'] = solicitada
        item['monto'] += amount
        for partida in partidas_guardadas(data):
            if partida not in item['partidas']:
                item['partidas'].append(partida)
    with almacen() as con:
        sent = con.execute("SELECT datos FROM envios WHERE documento=? AND tipo='rendicion'", (doc,)).fetchall()
        solicitudes = con.execute("SELECT id, creado, datos FROM envios WHERE documento=? AND tipo='solicitud'", (doc,)).fetchall()
    for row in solicitudes:
        datos = json.loads(row['datos'])
        if datos.get('estado') != 'Pagado':
            continue
        codigo = codigo_solicitud(row['id'])
        ref = _referencia(doc, codigo)
        grouped[ref] = {'referencia': ref, 'codigo': codigo, 'monto': Decimal(datos['monto']),
                        'motivo': datos['motivo'], 'estado': 'Pagado', 'fecha': datos.get('fecha_estado', '')[:10],
                        'fecha_solicitud': fecha_solicitud(row['creado']),
                        'partidas': partidas_guardadas(datos)}
    for item in grouped.values():
        reserved = sum((Decimal(json.loads(r['datos'])['monto']) for r in sent
                        if json.loads(r['datos']).get('referencia') == item['referencia']), Decimal('0'))
        item['pendiente'] = max(Decimal('0'), item['monto'] - reserved)
        item['enviado_prueba'] = str(reserved)
        item['monto'] = str(item['monto'])
        item['pendiente'] = str(item['pendiente'])
    return sorted(grouped.values(), key=lambda d: (d['fecha'], d['codigo']), reverse=True)


def pendientes_por_tecnico(alcance):
    from services.recursos_flm import familia

    consulta = (
        select(NucleusData.data_json).join(Proyecto, NucleusData.proyecto_id == Proyecto.id)
        .where(Proyecto.nombre == 'Rendicion').order_by(NucleusData.id.desc())
    )
    tecnicos = {}
    for raw in db.session.execute(consulta.execution_options(yield_per=500)).scalars():
        try:
            datos = json.loads(raw or '{}')
        except ValueError:
            continue
        if not isinstance(datos, dict) or estado_de(datos) in ('RECHAZADO', 'ANULADO'):
            continue
        etapa = etapa_de(datos)
        if etapa not in ('EVIDENCIA', 'OBSERVADO'):
            continue
        proyecto = familia(valor(datos, 'Nombre del proyecto', 'PROYECTO', 'CLIENTE'))
        if alcance is not None and proyecto not in alcance:
            continue
        doc = documento(valor(datos, 'Documento del beneficiario', 'Documento del beneficiario (Form)',
                              'Documento del beneficiario (Formulario)', 'DOCUMENTO', 'DNI'))
        codigo = str(valor(datos, 'CODIGO DEPOSITO')).strip()
        if not doc or not codigo:
            continue
        try:
            saldo = importe(valor(datos, 'MONTO PAGO'))
        except ValueError:
            continue
        nombre = str(valor(datos, 'Técnico beneficiario (Dataper)', 'Técnico beneficiario',
                           'Técnico beneficiario (Formulario)', 'Técnico beneficiario (Form)', 'TECNICO')).strip()
        tecnico = tecnicos.setdefault(doc, {'nombre': '', 'saldo': Decimal(0), 'depositos': {}})
        if nombre and not tecnico['nombre']:
            tecnico['nombre'] = nombre
        deposito = tecnico['depositos'].setdefault((proyecto, codigo), {
            'codigo': codigo, 'proyecto': proyecto or 'Sin proyecto', 'saldo': Decimal(0),
            'estado': 'Observado' if etapa == 'OBSERVADO' else 'Por rendir',
        })
        if etapa == 'OBSERVADO':
            deposito['estado'] = 'Observado'
        deposito['saldo'] += saldo
        tecnico['saldo'] += saldo
    indice = {}
    if any(not tecnico['nombre'] for tecnico in tecnicos.values()):
        from services.rendicion_personal import indice_personal
        indice = indice_personal()
    for doc, tecnico in tecnicos.items():
        nombres = {nombre for nombre, _ in indice.get(doc, []) if nombre}
        if not tecnico['nombre']:
            tecnico['nombre'] = nombres.pop() if len(nombres) == 1 else 'Técnico sin nombre registrado'
        tecnico['depositos'] = sorted(tecnico['depositos'].values(), key=lambda d: (-d['saldo'], d['codigo']))
    return sorted(tecnicos.values(), key=lambda t: (-t['saldo'], t['nombre'].casefold()))


def existente(doc, nonce):
    with almacen() as con:
        row = con.execute('SELECT id,tipo,datos FROM envios WHERE documento=? AND nonce=?', (doc, nonce)).fetchone()
    return dict(row) if row else None


def guardar(doc, tipo, data, nonce, uid, *, saldo=None, huellas=()):
    """Serializa rendiciones parciales para no sobrepasar el saldo del piloto."""
    with almacen() as con:
        con.execute('BEGIN IMMEDIATE')
        previous = con.execute('SELECT id FROM envios WHERE documento=? AND nonce=?', (doc, nonce)).fetchone()
        if previous:
            return previous['id'], False
        if saldo is not None:
            rows = con.execute("SELECT datos FROM envios WHERE documento=? AND tipo='rendicion'", (doc,)).fetchall()
            used = sum((Decimal(d['monto']) for r in rows
                        if (d := json.loads(r['datos'])).get('referencia') == data['referencia']), Decimal('0'))
            if used + Decimal(data['monto']) > saldo:
                raise ValueError('El saldo cambió. Actualiza tus depósitos antes de enviar.')
        if huellas:
            repetidas = 0
            comprobantes = (c for partida in data['partidas'] for c in partida['comprobantes'])
            for comprobante, huella in zip(comprobantes, huellas, strict=True):
                insercion = con.execute('INSERT OR IGNORE INTO huellas_comprobante VALUES (?)', (huella,))
                comprobante['foto_repetida'] = insercion.rowcount == 0
                repetidas += int(comprobante['foto_repetida'])
            data['fotos_comprobante_repetidas'] = repetidas
        con.execute('INSERT INTO envios VALUES(?,?,?,?,?,?)', (
            uid, doc, tipo, datetime.now(timezone.utc).isoformat(),
            json.dumps(data, ensure_ascii=False), nonce))
    return uid, True
