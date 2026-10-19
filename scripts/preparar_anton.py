"""Compara respaldos SQLite de Anton y Nucleus en modo estrictamente de lectura.

No importa la aplicación, no conecta con producción y no modifica las copias.
Los conteos locales de Anton son preliminares hasta confirmar su origen actual.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3


def abrir(path):
    path = Path(path).resolve(strict=True)
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    conn.execute('BEGIN')
    return conn


def nombre_destino(nombre):
    return 'FLM - PEXT' if nombre == 'PEXT' else nombre


def leer(conn):
    proyectos = {r['id']: r['nombre'] for r in conn.execute('SELECT id,nombre FROM proyectos')}
    registros = []
    for row in conn.execute('SELECT id,proyecto_id,key_value,data_json FROM nucleus_data'):
        registros.append({**dict(row), 'modulo': nombre_destino(proyectos[row['proyecto_id']]),
                          'datos': json.loads(row['data_json'])})
    return proyectos, registros


def comparar(origen, destino):
    with closing(abrir(origen)) as src, closing(abrir(destino)) as dst:
        ps, rs = leer(src)
        pd, rd = leer(dst)
        indice = {(r['modulo'], r['key_value']): r for r in rd}
        documentos = defaultdict(list)
        for row in rd:
            doc = str(row['datos'].get('DOCUMENTO') or '').strip()
            if row['modulo'] == 'Dataper' and doc:
                documentos[doc].append(row)
        conteos = defaultdict(Counter)
        for row in rs:
            modulo, datos = row['modulo'], row['datos']
            if modulo == 'Dataper':
                doc = str(datos.get('DOCUMENTO') or '').strip()
                matches = documentos.get(doc, []) if doc else []
                proyecto = nombre_destino(str(datos.get('PROYECTO') or '').strip())
                mismo_proyecto = [r for r in matches if
                    nombre_destino(str(r['datos'].get('PROYECTO') or '').strip()) == proyecto]
                estado = ('sin_documento' if not doc else 'persona_nueva' if not matches
                          else 'persona_existente_otro_proyecto' if not mismo_proyecto
                          else 'documento_ambiguo' if len(mismo_proyecto) > 1
                          else 'persona_existente_igual' if
                          {**mismo_proyecto[0]['datos'], 'PROYECTO': proyecto} == {**datos, 'PROYECTO': proyecto}
                          else 'persona_existente_con_diferencias')
            else:
                match = indice.get((modulo, row['key_value']))
                estado = ('clave_nueva' if match is None else
                          'coincidencia_exacta' if match['datos'] == datos else 'clave_conflictiva')
            conteos[modulo][estado] += 1
        fk = Counter(r[0] for r in src.execute('PRAGMA foreign_key_check'))
        usuarios = {r['username'].casefold(): r for r in dst.execute('SELECT username,nombre,rol FROM usuarios')}
        cuentas = Counter()
        for r in src.execute('SELECT username,nombre,rol FROM usuarios'):
            actual = usuarios.get(r['username'].casefold())
            estado = ('nueva' if actual is None else 'homonimo_revisar'
                      if (actual['nombre'] or '').strip().casefold() != (r['nombre'] or '').strip().casefold()
                      else 'mismo_usuario_rol_distinto' if actual['rol'] != r['rol'] else 'mismo_usuario')
            cuentas[estado] += 1
        return {
            'alcance': 'Preparación sobre respaldos; no ejecuta importación ni certifica la vigencia del origen.',
            'mapeo_catalogos': {n: nombre_destino(n) for n in ps.values()},
            'catalogos_ausentes_destino': sorted({nombre_destino(n) for n in ps.values()} - set(pd.values())),
            'registros_origen': len(rs), 'registros_destino': len(rd),
            'comparacion_por_modulo': {k: dict(v) for k, v in conteos.items()},
            'referencias_rotas_origen_por_tabla': dict(fk),
            'integridad_origen': [r[0] for r in src.execute('PRAGMA integrity_check')],
            'cuentas': dict(cuentas),
            'advertencias': ['Revisar el formato propio de PEXT y cotizaciones antes de adaptar un importador.',
                            'Inventariar B2 antes de descargar; aprovechar respaldos existentes y evitar agotar la cuota.',
                            'Conservar la procedencia de Anton separada de migracion_modus_origen.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anton', type=Path, required=True)
    parser.add_argument('--nucleus', type=Path, required=True)
    parser.add_argument('--salida', type=Path, required=True)
    args = parser.parse_args()
    resultado = comparar(args.anton, args.nucleus)
    with args.salida.open('x', encoding='utf-8') as file:
        json.dump(resultado, file, ensure_ascii=False, indent=2)
    print(json.dumps({'solo_lectura': True, 'filas_origen': resultado['registros_origen'],
                      'filas_destino': resultado['registros_destino'],
                      'referencias_rotas_origen': sum(resultado['referencias_rotas_origen_por_tabla'].values())}))
