"""Recupera PDFs detectados en el diario de reparación y enlaza su extensión real.

Usa un respaldo previo y compara cada fila al actualizar. No borra objetos ni filas.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request

import boto3
from botocore.config import Config
import psycopg2
from pypdf import PdfReader


def ejecutar(args):
    c = json.loads(args.accesos.read_text(encoding='utf-8-sig'))
    b2 = boto3.client('s3', endpoint_url=c['B2_ENDPOINT_URL'], aws_access_key_id=c['B2_KEY_ID'],
        aws_secret_access_key=c['B2_APP_KEY'], region_name=c['B2_REGION'],
        config=Config(connect_timeout=10, read_timeout=30, max_pool_connections=4, retries={'max_attempts': 2}))
    salida = args.reparacion / 'pdf-recuperados'
    salida.mkdir(exist_ok=True)

    def recuperar(f):
        d = json.loads(f.read_text(encoding='utf-8'))
        previo = salida / (f.stem + '.json')
        if previo.exists():
            estado_previo = json.loads(previo.read_text(encoding='utf-8'))['estado']
            if estado_previo == 'pdf_restaurado_y_enlazado':
                return estado_previo
        datos = (args.reparacion / 'objetos' / (f.stem + '.antes.bin')).read_bytes()
        ids = re.findall(rb'(?:/file/d/|/d/|[?&]id=)([A-Za-z0-9_-]{20,})', datos)
        if not ids:
            return 'sin_original'
        fid = ids[0].decode()
        pdf = None
        for url in (f'https://drive.google.com/uc?export=download&id={fid}',
                    f'https://drive.usercontent.google.com/download?id={fid}&export=download'):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as resp:
                    candidato = resp.read(25 * 1024 * 1024 + 1)
                if len(candidato) <= 25 * 1024 * 1024 and candidato.startswith(b'%PDF-') and len(PdfReader(io.BytesIO(candidato)).pages):
                    pdf = candidato
                    break
            except Exception:
                continue
        if pdf is None:
            return 'original_no_es_pdf_disponible'
        destino = d['destino'].rsplit('.', 1)[0] + '.pdf'
        (salida / (f.stem + '.pdf')).write_bytes(pdf)
        resultado = {'destino': destino, 'registros': d['registros'], 'sha256': hashlib.sha256(pdf).hexdigest(), 'estado': 'pdf_preparado'}
        previo.write_text(json.dumps(resultado), encoding='utf-8')
        if args.aplicar:
            # Los PDFs se crean con extensión propia; el objeto anterior se conserva.
            b2.put_object(Bucket=c['B2_BUCKET'], Key=destino, Body=pdf, ContentType='application/pdf')
            objeto = b2.get_object(Bucket=c['B2_BUCKET'], Key=destino)
            try:
                verificado = objeto['Body'].read()
            finally:
                objeto['Body'].close()
            if hashlib.sha256(verificado).hexdigest() != resultado['sha256']:
                raise ValueError('No coincide el PDF recuperado')
            with psycopg2.connect(c['DATABASE_URL'], connect_timeout=15) as conn:
                with conn.cursor() as cur:
                    for rid in set(d['registros']):
                        cur.execute('SELECT proyecto_id,data_json FROM nucleus_data WHERE id=%s FOR UPDATE', (rid,))
                        fila = cur.fetchone()
                        if not fila:
                            continue
                        pid, anterior = fila
                        (salida / (str(rid) + '.antes-db.json')).write_text(anterior, encoding='utf-8') if not (salida / (str(rid) + '.antes-db.json')).exists() else None
                        ruta = f'/api/rendicion/foto/{pid}/'
                        nuevo = anterior.replace(ruta + d['destino'], ruta + destino)
                        if nuevo != anterior:
                            cur.execute('UPDATE nucleus_data SET data_json=%s WHERE id=%s AND data_json=%s', (nuevo, rid, anterior))
                            if cur.rowcount != 1:
                                raise ValueError('El registro cambió durante la reparación')
            resultado['estado'] = 'pdf_restaurado_y_enlazado'
            previo.write_text(json.dumps(resultado), encoding='utf-8')
        return resultado['estado']

    pendientes = [f for f in (args.reparacion / 'diario').glob('*.json')
                  if json.loads(f.read_text(encoding='utf-8')).get('estado') == 'original_drive_no_disponible']
    from collections import Counter
    with ThreadPoolExecutor(max_workers=4) as grupo:
        print(json.dumps(dict(Counter(grupo.map(recuperar, pendientes)))), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--accesos', type=Path, required=True)
    p.add_argument('--reparacion', type=Path, required=True)
    p.add_argument('--aplicar', action='store_true')
    ejecutar(p.parse_args())
