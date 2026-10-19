"""Inventario de referencias a adjuntos; SQLite de solo lectura, sin modificar datos.

Uso: python scripts/auditar_adjuntos.py nucleus.db
No confirma existencia remota: las credenciales de B2/Render no se usan.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlsplit

from werkzeug.utils import secure_filename


def auditar(ruta):
    referencias = Counter()
    transformadas = Counter()
    carpetas = defaultdict(set)
    registros = 0
    with sqlite3.connect(Path(ruta).resolve().as_uri() + '?mode=ro', uri=True) as conexion:
        for pid, key, contenido in conexion.execute('SELECT proyecto_id,key_value,data_json FROM nucleus_data'):
            registros += 1
            carpetas[(pid, secure_filename(key))].add(key)
            urls = set(re.findall(r'/api/(?:rendicion/foto|rendicion/correo|evidencia/foto|cotizacion/correo)/[^\s"<>\\]+', contenido or ''))
            for url in urls:
                tipo = '/'.join(unquote(urlsplit(url).path).split('/')[2:4])
                referencias[tipo] += 1
                if tipo.endswith('/foto') and key != secure_filename(key):
                    transformadas[tipo] += 1
    return {
        'registros_revisados': registros,
        'referencias_por_tipo': dict(referencias),
        'referencias_con_clave_transformada': dict(transformadas),
        'colisiones_de_carpeta_en_mismo_proyecto': sum(len(v) > 1 for v in carpetas.values()),
        'existencia_remota': 'Pendiente de comprobar en Render/B2; este inventario no declara archivos perdidos.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    print(json.dumps(auditar(parser.parse_args().base), ensure_ascii=False, indent=2))
