"""Reúne fuentes LOCALES en staging con procedencia; nunca importa a producción.

Cada registro conserva sistema, tabla e identidad original. Los IDs iguales
de distintos sistemas permanecen separados. No decide fusiones ni permisos.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sqlite3


def preparar(fuentes, destino):
    destino = Path(destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('xb'):
        pass
    manifiesto = {'alcance':'STAGING de copias locales; no es una migración a Nucleus',
                  'adjuntos_descargados':False,'origenes':{}}
    with sqlite3.connect(destino) as dst:
        dst.execute('''CREATE TABLE registros_origen(
            sistema TEXT NOT NULL, tabla TEXT NOT NULL, identidad TEXT NOT NULL,
            datos_json TEXT NOT NULL, sha256 TEXT NOT NULL,
            PRIMARY KEY(sistema,tabla,identidad))''')
        for sistema, ruta in fuentes.items():
            ruta = Path(ruta).resolve(strict=True)
            tablas = {}
            with sqlite3.connect('file:' + ruta.as_posix() + '?mode=ro',uri=True) as src:
                src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
                relaciones = list(src.execute('PRAGMA foreign_key_check'))
                for (tabla,) in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
                    q = '"' + tabla.replace('"','""') + '"'
                    info = src.execute('PRAGMA table_info(' + q + ')').fetchall()
                    claves = [f[1] for f in sorted(info,key=lambda f:f[5]) if f[5]]
                    cursor = src.execute('SELECT * FROM ' + q)
                    columnas = [c[0] for c in cursor.description]
                    total = 0
                    for numero, fila in enumerate(cursor,1):
                        datos = dict(zip(columnas,fila))
                        identidad = json.dumps([datos[k] for k in claves] if claves else ['fila',numero],ensure_ascii=False)
                        contenido = json.dumps(datos,ensure_ascii=False,sort_keys=True,
                            default=lambda v:{'_tipo':'bytes','base64':base64.b64encode(v).decode()})
                        huella = hashlib.sha256(contenido.encode()).hexdigest()
                        dst.execute('INSERT INTO registros_origen VALUES(?,?,?,?,?)',
                                    (sistema,tabla,identidad,contenido,huella))
                        total += 1
                    tablas[tabla] = total
                manifiesto['origenes'][sistema] = {'tablas':tablas,'relaciones_pendientes':len(relaciones)}
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Falló la integridad del staging.')
        esperado = sum(sum(o['tablas'].values()) for o in manifiesto['origenes'].values())
        if dst.execute('SELECT COUNT(*) FROM registros_origen').fetchone()[0] != esperado:
            raise ValueError('No coincide el conteo del staging.')
    with destino.open('rb') as archivo:
        manifiesto['sha256'] = hashlib.file_digest(archivo,'sha256').hexdigest()
    destino.with_suffix('.manifest.json').write_text(json.dumps(manifiesto,indent=2),encoding='utf-8')
    return manifiesto


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anton',type=Path,required=True)
    parser.add_argument('--modus',type=Path,required=True)
    parser.add_argument('--destino',type=Path,required=True)
    args = parser.parse_args()
    informe = preparar({'Anton':args.anton,'Modus':args.modus},args.destino)
    print('Staging creado. Filas preservadas:',sum(sum(o['tablas'].values()) for o in informe['origenes'].values()))
    print('No se han fusionado registros ni modificado Nucleus.')
