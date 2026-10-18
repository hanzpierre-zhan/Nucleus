import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'copia_datos_local', Path(__file__).resolve().parents[1] / 'scripts/copia_datos_local.py')
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


def test_copia_preserva_ids_relaciones_y_todas_las_tablas(tmp_path):
    origen, destino = tmp_path / 'origen.db', tmp_path / 'copia.db'
    with sqlite3.connect(origen) as con:
        con.executescript('''
            CREATE TABLE proyectos(id INTEGER PRIMARY KEY, nombre TEXT);
            CREATE TABLE registros(id INTEGER PRIMARY KEY, proyecto_id INTEGER
                REFERENCES proyectos(id), data_json TEXT);
            CREATE TABLE auditoria(id INTEGER PRIMARY KEY, registro_id INTEGER
                REFERENCES registros(id));
            INSERT INTO proyectos VALUES(7, 'Claro');
            INSERT INTO registros VALUES(91, 7, '{"ESTADO":"DEPOSITADO"}');
            INSERT INTO auditoria VALUES(12, 91);
        ''')
    antes = origen.read_bytes()
    informe = modulo.copiar('sqlite:///' + origen.as_posix(), destino)
    assert origen.read_bytes() == antes
    assert informe['tablas'] == {'proyectos': 1, 'registros': 1, 'auditoria': 1}
    with sqlite3.connect(destino) as con:
        assert con.execute('SELECT id,proyecto_id FROM registros').fetchall() == [(91, 7)]
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        assert con.execute('SELECT registro_id FROM auditoria').fetchone() == (91,)
    assert json.loads(destino.with_suffix('.manifest.json').read_text())['sha256']
    with pytest.raises(FileExistsError):
        modulo.copiar('sqlite:///' + origen.as_posix(), destino)


def test_relacion_rota_no_genera_manifiesto_de_exito(tmp_path):
    origen, destino = tmp_path / 'origen.db', tmp_path / 'copia.db'
    with sqlite3.connect(origen) as con:
        con.executescript('''CREATE TABLE padre(id INTEGER PRIMARY KEY);
            CREATE TABLE hijo(id INTEGER PRIMARY KEY, padre_id INTEGER REFERENCES padre(id));
            INSERT INTO hijo VALUES(1, 999);''')
    with pytest.raises(ValueError):
        modulo.copiar('sqlite:///' + origen.as_posix(), destino)
    assert not destino.with_suffix('.manifest.json').exists()


def test_copia_esquema_actual_de_nucleus(app, tmp_path):
    from db import db
    from sqlalchemy import create_engine, inspect
    # Esquema real en una fuente propia: otros ensayos pueden dejar auditorías
    # históricas de usuarios temporales, y no son la fuente de esta prueba.
    engine = create_engine('sqlite:///' + (tmp_path / 'fuente-nucleus.db').as_posix())
    with app.app_context():
        db.metadata.create_all(engine)
        with engine.begin() as con:
            con.execute(db.metadata.tables['proyectos'].insert(), {'id':7,'nombre':'Claro'})
            con.execute(db.metadata.tables['usuarios'].insert(), {'id':3,'username':'ensayo','password_hash':'prueba','rol':'gestor'})
        tablas = set(inspect(engine).get_table_names())
        informe = modulo.copiar(str(engine.url), tmp_path / 'nucleus.db')
    engine.dispose()
    assert set(informe['tablas']) == tablas
    assert informe['tablas']['proyectos'] > 0
    assert informe['tablas']['usuarios'] > 0
    assert {'conformidad_usuario', 'refacturable_detalle',
            'liquidacion_numero', 'notificaciones'} <= tablas
