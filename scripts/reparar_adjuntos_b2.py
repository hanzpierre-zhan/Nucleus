"""Audita fotos referenciadas en un respaldo y recupera copias HTML de Drive.

Solo modifica B2 al indicar --aplicar. Conserva originales y un diario por objeto.
El archivo de accesos y los respaldos deben mantenerse fuera de Git.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
from pathlib import Path
import re
import threading
from urllib.parse import unquote, urlsplit
import urllib.request

import boto3
from botocore.config import Config
from PIL import Image, ImageOps


def imagen_valida(datos):
    try:
        with Image.open(io.BytesIO(datos)) as imagen:
            imagen.verify()
        return True
    except Exception:
        return False


def referencias(filas):
    resultado = {}
    for fila in filas:
        texto = json.dumps(fila['data_json'], ensure_ascii=False)
        for url in set(re.findall(r'/api/(?:rendicion|evidencia)/foto/[^\s"<>\\]+', texto)):
            ruta = unquote(urlsplit(url).path)
            m = re.match(r'^/api/(rendicion|evidencia)/foto/(\d+)/(.*)/([^/]+)$', ruta)
            if not m:
                continue
            modulo, pid, clave, nombre = m.groups()
            destino = clave + '/' + nombre
            entrada = resultado.setdefault(destino, {'destino': destino, 'modulo': modulo, 'candidatos': [], 'registros': []})
            for candidato in (destino, str(fila['key_value']) + '/' + nombre):
                if candidato not in entrada['candidatos']:
                    entrada['candidatos'].append(candidato)
            entrada['registros'].append(fila['id'])
    return list(resultado.values())


def ejecutar(args):
    acceso = json.loads(args.accesos.read_text(encoding='utf-8-sig'))
    filas = json.loads(args.referencias.read_text(encoding='utf-8'))
    inventario = json.loads(args.inventario.read_text(encoding='utf-8'))
    salida = args.salida
    salida.mkdir(parents=True, exist_ok=True)
    objetos = salida / 'objetos'
    objetos.mkdir(exist_ok=True)
    diario = salida / 'diario'
    diario.mkdir(exist_ok=True)
    cliente = boto3.client('s3', endpoint_url=acceso['B2_ENDPOINT_URL'],
        aws_access_key_id=acceso['B2_KEY_ID'], aws_secret_access_key=acceso['B2_APP_KEY'],
        region_name=acceso['B2_REGION'], config=Config(connect_timeout=10, read_timeout=35,
        max_pool_connections=args.hilos, retries={'max_attempts': 2}))
    bucket = acceso['B2_BUCKET']
    bloqueo = threading.Lock()
    detenido = threading.Event()
    lecturas = 0

    def leer(clave):
        nonlocal lecturas
        with bloqueo:
            if detenido.is_set() or lecturas >= args.max_lecturas:
                raise RuntimeError('Auditoría detenida por presupuesto de lecturas')
            lecturas += 1
        try:
            respuesta = cliente.get_object(Bucket=bucket, Key=clave)
        except Exception as error:
            mensaje = str(getattr(error, 'response', {}).get('Error', {}).get('Message', '')).lower()
            if 'cap exceeded' in mensaje:
                detenido.set()
            raise
        try:
            return respuesta['Body'].read(25 * 1024 * 1024 + 1)
        finally:
            respuesta['Body'].close()

    def procesar(entrada):
        destino = entrada['destino']
        token = hashlib.sha256(destino.encode()).hexdigest()
        resultado = dict(entrada)
        try:
            existentes = [k for k in entrada['candidatos'] if k in inventario]
            if not existentes:
                resultado['estado'] = 'sin_objeto_b2'
                return resultado
            origen = existentes[0]
            datos = leer(origen)
            resultado['origen'] = origen
            if imagen_valida(datos):
                if origen == destino:
                    resultado['estado'] = 'imagen_valida'
                    return resultado
                nuevos = datos
                resultado['tipo_reparacion'] = 'alias_de_ruta'
            else:
                ids = list(dict.fromkeys(re.findall(rb'(?:/file/d/|/d/|[?&]id=)([A-Za-z0-9_-]{20,})', datos)))
                if not ids or (b'<html' not in datos[:2000].lower() and b'<!doctype html' not in datos[:2000].lower()):
                    resultado['estado'] = 'contenido_no_reconocido'
                    return resultado
                (objetos / (token + '.antes.bin')).write_bytes(datos)
                resultado['sha256_antes'] = hashlib.sha256(datos).hexdigest()
                fid = ids[0].decode()
                recuperado = None
                for url in (f'https://drive.google.com/uc?export=download&id={fid}',
                            f'https://drive.usercontent.google.com/download?id={fid}&export=download',
                            f'https://lh3.googleusercontent.com/d/{fid}=s0'):
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=25) as respuesta:
                            candidato = respuesta.read(25 * 1024 * 1024 + 1)
                        if len(candidato) <= 25 * 1024 * 1024 and imagen_valida(candidato):
                            recuperado = candidato
                            break
                    except Exception:
                        continue
                if recuperado is None:
                    resultado['estado'] = 'original_drive_no_disponible'
                    return resultado
                (objetos / (token + '.original')).write_bytes(recuperado)
                with Image.open(io.BytesIO(recuperado)) as imagen:
                    imagen = ImageOps.exif_transpose(imagen).convert('RGB')
                    imagen.thumbnail((1280, 1280))
                    memoria = io.BytesIO()
                    imagen.save(memoria, 'JPEG', quality=80, optimize=True)
                    nuevos = memoria.getvalue()
                resultado['tipo_reparacion'] = 'imagen_recuperada_de_drive'
            (objetos / (token + '.restaurado')).write_bytes(nuevos)
            resultado['sha256_restaurado'] = hashlib.sha256(nuevos).hexdigest()
            resultado['estado'] = 'reparacion_preparada'
            # Guardar el diario ANTES de escribir en B2.
            (diario / (token + '.json')).write_text(json.dumps(resultado, ensure_ascii=False), encoding='utf-8')
            if args.aplicar:
                if destino in inventario and destino != origen:
                    (objetos / (token + '.destino-antes.bin')).write_bytes(leer(destino))
                elif origen == destino and not (objetos / (token + '.antes.bin')).exists():
                    (objetos / (token + '.antes.bin')).write_bytes(datos)
                with Image.open(io.BytesIO(nuevos)) as imagen:
                    tipo = Image.MIME.get(imagen.format, 'application/octet-stream')
                cliente.put_object(Bucket=bucket, Key=destino, Body=nuevos, ContentType=tipo,
                                   CacheControl='private, max-age=0, must-revalidate')
                verificado = leer(destino)
                if hashlib.sha256(verificado).hexdigest() != resultado['sha256_restaurado'] or not imagen_valida(verificado):
                    raise ValueError('La verificación posterior no coincide')
                resultado['estado'] = 'reparado_y_verificado'
            return resultado
        except Exception as error:
            resultado['estado'] = 'error'
            resultado['error_tipo'] = type(error).__name__
            return resultado
        finally:
            (diario / (token + '.json')).write_text(json.dumps(resultado, ensure_ascii=False), encoding='utf-8')

    pendientes = referencias(filas)
    if args.modulo:
        pendientes = [r for r in pendientes if r['modulo'] == args.modulo]
    pendientes.sort(key=lambda r: ('1_10_2026_164009' not in r['destino'], r['destino']))
    conteo = Counter()
    with ThreadPoolExecutor(max_workers=args.hilos) as grupo:
        tareas = [grupo.submit(procesar, r) for r in pendientes]
        for i, tarea in enumerate(as_completed(tareas), 1):
            conteo[tarea.result()['estado']] += 1
            if i % 25 == 0 or i == len(tareas):
                print(json.dumps({'procesados': i, 'total': len(tareas), 'resultados': dict(conteo)}), flush=True)
    (salida / 'resumen.json').write_text(json.dumps(dict(conteo), indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for nombre in ('accesos', 'referencias', 'inventario', 'salida'):
        parser.add_argument('--' + nombre, required=True, type=Path)
    parser.add_argument('--modulo', choices=('rendicion', 'evidencia'))
    parser.add_argument('--hilos', type=int, default=6)
    parser.add_argument('--max-lecturas', type=int, default=100,
                        help='Presupuesto de descargas B2; aumentar explícitamente tras revisar Caps & Alerts.')
    parser.add_argument('--aplicar', action='store_true')
    ejecutar(parser.parse_args())
