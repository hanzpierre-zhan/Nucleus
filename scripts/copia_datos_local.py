"""Copia lógica de todas las tablas a un SQLite NUEVO, sin descargar adjuntos.

No importa la aplicación ni ejecuta migraciones. El origen se lee dentro de
una transacción consistente y de solo lectura. DATABASE_URL no se imprime.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text
from sqlalchemy.engine import make_url


def copiar(url, destino):
    destino = Path(destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Reserva exclusiva: nunca sobrescribir una base de trabajo o un respaldo.
    with destino.open('xb'):
        pass
    manifiesto = destino.with_suffix('.manifest.json')
    if manifiesto.exists():
        destino.unlink()
        raise ValueError('Ya existe el manifiesto de destino.')
    parsed = make_url(url)
    if parsed.drivername in ('postgres', 'postgresql'):
        parsed = parsed.set(drivername='postgresql+psycopg2')
    if parsed.get_backend_name() == 'sqlite':
        origen_path = Path(parsed.database).resolve()
        if not origen_path.is_file() or origen_path == destino:
            destino.unlink()
            raise ValueError('El origen SQLite debe existir y ser diferente al destino.')
        parsed = make_url('sqlite:///file:' + origen_path.as_posix() + '?mode=ro&uri=true')
    origen = create_engine(parsed)
    local = create_engine('sqlite:///' + destino.as_posix())
    informe = {'creado_utc': datetime.now(timezone.utc).isoformat(),
               'tipo': 'copia logica para pruebas; no sustituye un respaldo nativo',
               'adjuntos_descargados': False, 'tablas': {}}
    try:
        with origen.connect() as src:
            if src.dialect.name == 'postgresql':
                src = src.execution_options(isolation_level='REPEATABLE READ')
            with src.begin():
                if src.dialect.name == 'postgresql':
                    src.execute(text('SET TRANSACTION READ ONLY'))
                elif src.dialect.name == 'sqlite':
                    src.exec_driver_sql('PRAGMA query_only = ON')
                    # BEGIN explícito: sqlite3 no inicia snapshot con un SELECT.
                    src.exec_driver_sql('BEGIN')
                else:
                    raise ValueError('Solo se admite PostgreSQL o SQLite como origen.')
                esquema = MetaData()
                esquema.reflect(bind=src)
                copia = MetaData()
                for tabla in esquema.sorted_tables:
                    clon = tabla.to_metadata(copia)
                    for col in clon.columns:
                        col.type = col.type.as_generic()
                        col.server_default = None
                        col.identity = None
                    # Los índices no son necesarios para verificar los datos.
                    clon.indexes.clear()
                copia.create_all(local)
                with local.begin() as dst:
                    for tabla in esquema.sorted_tables:
                        clon = copia.tables[tabla.key]
                        esperado = src.scalar(select(func.count()).select_from(tabla))
                        filas = src.execute(select(tabla)).mappings()
                        total = 0
                        while lote := filas.fetchmany(1000):
                            dst.execute(clon.insert(), [dict(f) for f in lote])
                            total += len(lote)
                        recibido = dst.scalar(select(func.count()).select_from(clon))
                        if total != esperado or recibido != esperado:
                            raise ValueError('No coincide el conteo de una tabla.')
                        informe['tablas'][tabla.name] = recibido
                    if dst.exec_driver_sql('PRAGMA integrity_check').scalar() != 'ok':
                        raise ValueError('Falló la integridad SQLite.')
                    if dst.exec_driver_sql('PRAGMA foreign_key_check').fetchone():
                        raise ValueError('Existen relaciones sin su registro de referencia.')
        local.dispose()
        with destino.open('rb') as archivo:
            informe['sha256'] = hashlib.file_digest(archivo, 'sha256').hexdigest()
        with manifiesto.open('x', encoding='utf-8') as archivo:
            json.dump(informe, archivo, ensure_ascii=False, indent=2)
        return informe
    except Exception:
        local.dispose()
        # Se conserva el archivo parcial para diagnóstico, sin marcarlo verificado.
        raise
    finally:
        origen.dispose()
        local.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', required=True)
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        raise SystemExit('Falta DATABASE_URL. No se ha conectado ni copiado producción.')
    try:
        informe = copiar(url, args.destino)
    except Exception as error:
        # Las excepciones del driver pueden contener valores o credenciales.
        raise SystemExit('Copia no verificada: ' + type(error).__name__) from None
    print('Copia verificada: %d tablas, %d filas. Adjuntos no descargados.' %
          (len(informe['tablas']), sum(informe['tablas'].values())))


if __name__ == '__main__':
    main()
