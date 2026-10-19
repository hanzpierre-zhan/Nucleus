"""Adaptación y conciliación OFFLINE de cotizaciones de Anton.

Lee respaldos en modo solo lectura. Genera propuestas conservando ambas
versiones y nunca escribe en Nucleus ni sustituye decisiones de su flujo.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from scripts.preparar_anton import abrir, nombre_destino


def normalizar(texto):
    texto = unicodedata.normalize('NFKD', str(texto or ''))
    return ''.join(c for c in texto if not unicodedata.combining(c)).strip().casefold()


ESTADOS = {
    'pendiente de aprobacion': 'En Aprobación',
    'cotizacion rechazada': 'Rechazado',
}
ESTADOS_NUCLEUS = {'pdt. cotizacion', 'cotizado', 'en aprobacion', 'aprobado',
                   'atendido', 'cancelado', 'validado', 'observado', 'rechazado',
                   'en proceso', 'anulado', 'anulada'}
RUTA_ADJUNTO = re.compile(r'(/api/(?:evidencia/foto|cotizacion/correo)/)(\d+)(/)')


def adaptar(datos, proyectos=None):
    """Conserva valores originales; transforma solo estados y IDs de rutas.

    Un estado desconocido o ítems inválidos bloquean la propuesta de carga,
    en lugar de convertirlos silenciosamente en Registro o una lista vacía.
    """
    resultado = deepcopy(datos)
    incidencias = []
    advertencias = []
    estado = str(datos.get('ESTADO COTIZACION') or '').strip()
    clave_estado = normalizar(estado)
    if clave_estado in ESTADOS:
        resultado['ESTADO COTIZACION'] = ESTADOS[clave_estado]
        if clave_estado == 'pendiente de aprobacion' and str(datos.get('GENERADA') or '').strip() != '1':
            resultado['ESTADO COTIZACION'] = 'Pdt. Cotización'
            advertencias.append('sin_constancia_de_generacion_conservar_en_registro')
    elif clave_estado not in ESTADOS_NUCLEUS:
        incidencias.append('estado_sin_equivalencia')
    try:
        items = json.loads(datos.get('ITEMS_JSON') or '[]')
        if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
            raise ValueError('Se requiere lista de ítems')
    except (ValueError, TypeError):
        incidencias.append('items_invalidos')
    if proyectos is not None:
        def ruta(match):
            origen = int(match[2])
            if origen not in proyectos:
                incidencias.append('ruta_con_proyecto_sin_destino')
                return match[0]
            return match[1] + str(proyectos[origen]) + match[3]

        def transformar(valor):
            if isinstance(valor, dict):
                return {k: transformar(v) for k, v in valor.items()}
            if isinstance(valor, list):
                return [transformar(v) for v in valor]
            return RUTA_ADJUNTO.sub(ruta, valor) if isinstance(valor, str) else valor
        resultado = transformar(resultado)
    return {'datos': resultado, 'estado_original': estado,
            'incidencias': sorted(set(incidencias)), 'advertencias': advertencias}


def numero_px(original, ocupados):
    """Reserva una numeración PX única sin tocar la secuencia de Nucleus.

    El mapa resultante debe persistirse y reutilizarse durante la importación;
    no generar números nuevos al repetir una migración ya registrada.
    """
    original = str(original or '').strip()
    if not original:
        raise ValueError('Cotización sin número de origen')
    base = re.sub(r'^[A-Za-z]+[-–—]', 'PX-', original, count=1)
    if base == original and not original.upper().startswith('PX-'):
        base = 'PX-' + original
    numero, indice = base, 2
    while numero.casefold() in ocupados:
        numero = '%s-%02d' % (base, indice)
        indice += 1
    ocupados.add(numero.casefold())
    return numero


def wos(valor):
    return {v.strip().casefold() for v in re.split(r'[,;\n\r|]+', str(valor or '')) if v.strip()}


def valor_comparable(campo, valor):
    if campo == 'ITEMS_JSON':
        try:
            return json.loads(valor or '[]')
        except (ValueError, TypeError):
            return valor
    if campo == 'NUMERO WO':
        return wos(valor)
    if campo == 'CLIENTE':
        return normalizar(valor)
    return valor


def conciliar(origen, actual, proyectos=None):
    adaptacion = adaptar(origen, proyectos)
    propuesta = {'adaptacion': adaptacion, 'accion': 'agregar_nuevo' if actual is None else 'conservar_nucleus',
                 'campos_distintos': [], 'identidad_distinta': False}
    if actual is not None:
        propuesta['campos_distintos'] = sorted(k for k in origen.keys() | actual.keys()
            if valor_comparable(k, adaptacion['datos'].get(k)) != valor_comparable(k, actual.get(k)))
        for campo in ('CLIENTE', 'NUMERO WO'):
            a, b = valor_comparable(campo, origen.get(campo)), valor_comparable(campo, actual.get(campo))
            if a and b and a != b:
                propuesta['identidad_distinta'] = True
        if propuesta['identidad_distinta']:
            propuesta['accion'] = 'revisar_colision_de_clave'
    if adaptacion['incidencias']:
        propuesta['accion'] = 'bloqueado_por_validacion'
    return propuesta


def generar(origen_path, destino_path, renumerar_px=False):
    src, dst = abrir(origen_path), abrir(destino_path)
    try:
        sp = {r['id']: r['nombre'] for r in src.execute('SELECT id,nombre FROM proyectos')}
        dp = {r['nombre']: r['id'] for r in dst.execute('SELECT id,nombre FROM proyectos')}
        mapa = {id: dp[nombre_destino(n)] for id, n in sp.items() if nombre_destino(n) in dp}
        pid_src = next(id for id, n in sp.items() if n == 'Cotizaciones')
        pid_dst = dp['Cotizaciones']
        actuales = {r['key_value']: dict(r) for r in dst.execute('SELECT * FROM nucleus_data WHERE proyecto_id=?', (pid_dst,))}
        ocupados = {k.casefold() for k in actuales}
        for r in actuales.values():
            numero = json.loads(r['data_json']).get('N° COTIZACION')
            if numero:
                ocupados.add(str(numero).strip().casefold())
        ocupados.update(str(r[0]).strip().casefold() for r in dst.execute('SELECT numero FROM cotizaciones') if r[0])
        numeracion = {}
        anteriores = {}
        for registro in actuales.values():
            d = json.loads(registro['data_json'])
            if d.get('_MIGRACION_ANTON_ID') is not None:
                anteriores[int(d['_MIGRACION_ANTON_ID'])] = registro['key_value']
        indice_wo = defaultdict(set)
        for c, proyectos in [(dst, {id: n for n, id in dp.items()}), (src, sp)]:
            for r in c.execute('SELECT id,proyecto_id,key_value FROM nucleus_data'):
                nombre = nombre_destino(proyectos[r['proyecto_id']])
                if nombre.startswith('FLM - '):
                    indice_wo[(nombre, r['key_value'].strip().casefold())].add((nombre, r['key_value']))
        propuestas, resumen, enlaces = [], Counter(), Counter()
        for fila in src.execute('SELECT * FROM nucleus_data WHERE proyecto_id=? ORDER BY id', (pid_src,)):
            datos = json.loads(fila['data_json'])
            actual = actuales.get(fila['key_value'])
            a = json.loads(actual['data_json']) if actual else None
            propuesta = conciliar(datos, a, mapa)
            if renumerar_px:
                original = str(datos.get('N° COTIZACION') or fila['key_value'])
                numero = anteriores.get(fila['id']) or numero_px(original, ocupados)
                numeracion['nucleus_data:%s' % fila['id']] = {'original': original, 'numero_px': numero}
                adaptados = propuesta['adaptacion']['datos']
                adaptados['N° COTIZACION'] = numero
                adaptados['_MIGRACION_ANTON_ID'] = fila['id']
                adaptados['_MIGRACION_ANTON_CLAVE'] = fila['key_value']
                adaptados['_MIGRACION_ANTON_NUMERO'] = original
                # Los archivos de la cotización viajan a la carpeta del nuevo
                # número; las fotos de sus WOs conservan sus claves operativas.
                prefijo = r'(/api/(?:evidencia/foto|cotizacion/correo)/%s/)%s/' % (
                    mapa[pid_src], re.escape(fila['key_value']))
                serializado = json.dumps(adaptados, ensure_ascii=False)
                adaptados = json.loads(re.sub(prefijo, lambda m: m[1] + numero + '/', serializado))
                propuesta['adaptacion']['datos'] = adaptados
                propuesta['clave_destino'] = numero
                if not propuesta['adaptacion']['incidencias']:
                    propuesta['accion'] = 'agregar_con_prefijo_px'
            refs = wos(datos.get('NUMERO WO'))
            familia = 'FLM - ' + str(datos.get('CLIENTE') or '').strip().upper()
            relaciones = []
            for wo in sorted(refs):
                matches = indice_wo.get((familia, wo), set())
                relaciones.append({'wo': wo, 'coincidencias': len(matches)})
                enlaces['unica' if len(matches) == 1 else 'sin_coincidencia' if not matches else 'ambigua'] += 1
            if not refs:
                enlaces['sin_wo_declarada'] += 1
            resumen[propuesta['accion']] += 1
            propuestas.append({'id_anton': fila['id'], 'clave_original': fila['key_value'],
                'id_nucleus': actual['id'] if actual else None,
                'sha256_original': hashlib.sha256(fila['data_json'].encode()).hexdigest(),
                'original_anton': datos, 'actual_nucleus': a,
                'relaciones_wo': relaciones, **propuesta})
        # Cotizaciones generadas desde PEXT: otra tabla, otro formato.
        fisicas = []
        for r in src.execute('SELECT * FROM cotizaciones ORDER BY id'):
            row = dict(r)
            pid = row['proyecto_id']
            existe = src.execute('SELECT id FROM nucleus_data WHERE proyecto_id=? AND key_value=?',
                                 (pid, row['key_value'])).fetchone()
            adaptada = {**row, 'proyecto_id': mapa.get(pid)}
            if renumerar_px:
                numero_anterior = None
                if dst.execute("SELECT 1 FROM sqlite_master WHERE name='migracion_anton_origen'").fetchone():
                    previo = dst.execute("SELECT id_destino FROM migracion_anton_origen WHERE tabla='cotizaciones' AND id_origen=?", (str(row['id']),)).fetchone()
                    if previo:
                        numero_anterior = dst.execute('SELECT numero FROM cotizaciones WHERE id=?', (int(previo[0]),)).fetchone()[0]
                numero = numero_anterior or numero_px(row['numero'], ocupados)
                adaptada['numero'] = numero
                numeracion['cotizaciones:%s' % row['id']] = {'original': row['numero'], 'numero_px': numero}
            fisicas.append({'id_anton': row['id'], 'modulo': nombre_destino(sp[pid]),
                'proyecto_destino': mapa.get(pid), 'wo_existe_en_origen': existe is not None,
                'formato': row['formato'] or 'huawei', 'original': row, 'adaptada': adaptada,
                'accion': 'conservar_formato_y_remapear_proyecto'})
        return {'alcance': 'Propuestas offline; sin escrituras en origen ni destino',
            'resumen': dict(resumen), 'relaciones_wo': dict(enlaces), 'numeracion': numeracion,
            'cotizaciones_modulo': propuestas, 'cotizaciones_desde_wo': fisicas}
    finally:
        src.close()
        dst.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anton', type=Path, required=True)
    parser.add_argument('--nucleus', type=Path, required=True)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--prefijo-px', action='store_true')
    args = parser.parse_args()
    informe = generar(args.anton, args.nucleus, renumerar_px=args.prefijo_px)
    with args.salida.open('x', encoding='utf-8') as file:
        json.dump(informe, file, ensure_ascii=False, indent=2)
    print(json.dumps({'acciones': informe['resumen'], 'relaciones_wo': informe['relaciones_wo'],
                      'cotizaciones_desde_wo': len(informe['cotizaciones_desde_wo'])}))
