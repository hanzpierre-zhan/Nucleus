import importlib.util
from pathlib import Path
import sqlite3

spec = importlib.util.spec_from_file_location('preparar_absorcion',
    Path(__file__).resolve().parents[1] / 'scripts/preparar_absorcion.py')
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


def test_ids_repetidos_no_se_fusionan_y_origen_no_se_modifica(tmp_path):
    fuentes = {}
    for nombre in ('Anton','Modus'):
        path = tmp_path / (nombre + '.db')
        with sqlite3.connect(path) as con:
            con.executescript("CREATE TABLE usuarios(id INTEGER PRIMARY KEY,nombre TEXT); INSERT INTO usuarios VALUES(1,'Persona');")
        fuentes[nombre] = path
    originales = {n:p.read_bytes() for n,p in fuentes.items()}
    destino = tmp_path / 'staging.db'
    informe = modulo.preparar(fuentes,destino)
    with sqlite3.connect(destino) as con:
        assert con.execute('SELECT sistema,identidad FROM registros_origen ORDER BY sistema').fetchall() == [('Anton','[1]'),('Modus','[1]')]
    assert sum(sum(o['tablas'].values()) for o in informe['origenes'].values()) == 2
    assert all(p.read_bytes() == originales[n] for n,p in fuentes.items())
