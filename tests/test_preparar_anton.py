import hashlib
import json
import sqlite3

import pytest

from scripts.preparar_anton import abrir, comparar


def crear(path, origen):
    with sqlite3.connect(path) as c:
        c.executescript('''
            CREATE TABLE proyectos(id INTEGER PRIMARY KEY,nombre TEXT);
            CREATE TABLE nucleus_data(id INTEGER PRIMARY KEY,proyecto_id INTEGER,
                key_value TEXT,data_json TEXT);
            CREATE TABLE usuarios(id INTEGER PRIMARY KEY,username TEXT,nombre TEXT,rol TEXT);
        ''')
        c.executemany('INSERT INTO proyectos VALUES(?,?)', [(1, 'PEXT' if origen else 'FLM - PEXT'), (2, 'Dataper')])
        c.execute('INSERT INTO nucleus_data VALUES(1,1,?,?)', ('WO-1', '{"estado":"igual"}'))
        c.execute('INSERT INTO nucleus_data VALUES(2,2,?,?)', (
            'clave_origen' if origen else 'otra_clave',
            json.dumps({'DOCUMENTO': '12345678', 'TECNICO': 'Origen' if origen else 'Actual'})))
        c.execute('INSERT INTO usuarios VALUES(1,?,?,?)', ('usuario', 'Origen' if origen else 'Actual', 'supervisor'))


def test_compara_documento_y_proyecto_sin_modificar_bases(tmp_path):
    src, dst = tmp_path / 'anton.db', tmp_path / 'nucleus.db'
    crear(src, True)
    crear(dst, False)
    antes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (src, dst)]
    informe = comparar(src, dst)
    assert informe['mapeo_catalogos']['PEXT'] == 'FLM - PEXT'
    assert informe['comparacion_por_modulo']['FLM - PEXT']['coincidencia_exacta'] == 1
    assert informe['comparacion_por_modulo']['Dataper']['persona_existente_con_diferencias'] == 1
    assert informe['cuentas']['homonimo_revisar'] == 1
    assert antes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (src, dst)]


def test_conexion_rechaza_escrituras_y_no_crea_archivos(tmp_path):
    src = tmp_path / 'anton.db'
    crear(src, True)
    with abrir(src) as c:
        with pytest.raises(sqlite3.OperationalError):
            c.execute('DELETE FROM usuarios')
    inexistente = tmp_path / 'no_existe.db'
    with pytest.raises(FileNotFoundError):
        abrir(inexistente)
    assert not inexistente.exists()


def test_mismo_documento_otro_proyecto_requiere_asociacion_separada(tmp_path):
    src, dst = tmp_path / 'anton.db', tmp_path / 'nucleus.db'
    crear(src, True)
    crear(dst, False)
    for file, proyecto in [(src, 'PEXT'), (dst, 'FLM - ENTEL')]:
        with sqlite3.connect(file) as c:
            datos = json.loads(c.execute('SELECT data_json FROM nucleus_data WHERE id=2').fetchone()[0])
            datos['PROYECTO'] = proyecto
            c.execute('UPDATE nucleus_data SET data_json=? WHERE id=2', (json.dumps(datos),))
    informe = comparar(src, dst)
    assert informe['comparacion_por_modulo']['Dataper'] == {'persona_existente_otro_proyecto': 1}
