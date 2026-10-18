import importlib.util
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

spec=importlib.util.spec_from_file_location('restaurar_exportacion',Path(__file__).resolve().parents[1]/'scripts/restaurar_exportacion.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def exportacion(path,conteo=1):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('manifest.json',json.dumps({'tablas':{'usuarios':1,'proyectos':1,'nucleus_data':conteo}}))
        z.writestr('usuarios.json',json.dumps([{'id':17,'username':'prueba','nombre':'Prueba','password_hash':'hash','rol':'supervisor'}]))
        z.writestr('proyectos.json',json.dumps([{'id':41,'nombre':'Rendicion','descripcion':'','icono':'fa-folder'}]))
        z.writestr('nucleus_data_p41.json',json.dumps([{'id':935,'proyecto_id':41,'key_value':'FECHA','data_json':'{"ESTADO":"DEPOSITADO"}'}]))


def test_restaura_conteos_e_ids_originales_sin_mezclar_datos(tmp_path):
    zip_path=tmp_path/'origen.zip';destino=tmp_path/'copia.db';exportacion(zip_path)
    r=mod.restaurar(zip_path,destino)
    assert r['tablas']['nucleus_data']==1
    with sqlite3.connect(destino) as c:
        assert c.execute('SELECT id,proyecto_id FROM nucleus_data').fetchall()==[(935,41)]
        assert c.execute('SELECT id FROM usuarios').fetchall()==[(17,)]
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_rechaza_exportacion_truncada_sin_manifiesto_de_exito(tmp_path):
    zip_path=tmp_path/'origen.zip';destino=tmp_path/'copia.db';exportacion(zip_path,conteo=9)
    with pytest.raises(ValueError):mod.restaurar(zip_path,destino)
    assert not destino.with_suffix('.manifest.json').exists()
