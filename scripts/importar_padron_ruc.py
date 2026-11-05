"""Indexa el ZIP oficial de SUNAT para la consulta de RUC en el portal."""
import argparse
import io
import sqlite3
import tempfile
from pathlib import Path
from zipfile import ZipFile


def importar(origen, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino.parent) as carpeta:
        temporal = Path(carpeta) / destino.name
        with ZipFile(origen) as zip_ruc:
            archivos = [nombre for nombre in zip_ruc.namelist() if nombre.lower().endswith('.txt')]
            if len(archivos) != 1:
                raise ValueError('El ZIP debe contener el archivo TXT del padrón reducido de RUC.')
            con = sqlite3.connect(temporal)
            try:
                with con, zip_ruc.open(archivos[0]) as bruto:
                    con.execute('CREATE TABLE ruc (numero TEXT PRIMARY KEY, razon_social TEXT, estado TEXT, '
                                'condicion TEXT) WITHOUT ROWID')
                    lineas = io.TextIOWrapper(bruto, encoding='latin-1')
                    encabezado = next(lineas, '').strip().upper().split('|')
                    if len(encabezado) < 4 or 'RUC' not in encabezado[0]:
                        raise ValueError('No se reconoce el encabezado del padrón de SUNAT.')
                    filas = (linea.strip().split('|', 4)[:4] for linea in lineas if linea.strip())
                    total = con.executemany('INSERT INTO ruc VALUES (?, ?, ?, ?)', filas).rowcount
                    if not total:
                        raise ValueError('El padrón no contiene contribuyentes.')
            finally:
                con.close()
        temporal.replace(destino)
    return total


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip_sunat', type=Path)
    parser.add_argument('directorio_piloto', type=Path)
    args = parser.parse_args()
    total = importar(args.zip_sunat, args.directorio_piloto / 'padron-ruc.sqlite3')
    print(f'RUC importados: {total:,}')
