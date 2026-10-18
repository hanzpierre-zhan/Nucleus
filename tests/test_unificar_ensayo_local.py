import importlib.util
import json
from pathlib import Path
import sqlite3

spec=importlib.util.spec_from_file_location('unificar_ensayo_local',Path(__file__).resolve().parents[1]/'scripts/unificar_ensayo_local.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def test_unificacion_remapea_ids_preserva_conflictos_y_origenes(app,tmp_path):
    from db import db
    from sqlalchemy import create_engine
    paths={n:tmp_path/(n+'.db') for n in ('base','Modus','Anton')}
    with app.app_context():
        for nombre,path in paths.items():
            engine=create_engine('sqlite:///'+path.as_posix());db.metadata.create_all(engine)
            with engine.begin() as c:
                c.execute(db.metadata.tables['usuarios'].insert(),{'id':1,'username':'admin' if nombre=='base' else 'gestor','password_hash':'hash','rol':'gestor'})
                c.execute(db.metadata.tables['proyectos'].insert(),{'id':1,'nombre':'Rendicion' if nombre=='base' else 'FLM - INTEGRATEL'})
                if nombre!='base':
                    c.execute(db.metadata.tables['nucleus_data'].insert(),{'id':1,'proyecto_id':1,'key_value':'MISMA-CLAVE','data_json':json.dumps({'origen':nombre})})
            engine.dispose()
    originales={n:p.read_bytes() for n,p in paths.items()}
    destino=tmp_path/'unificado.db'
    r=mod.unificar(paths['base'],{'Modus':paths['Modus'],'Anton':paths['Anton']},destino)
    assert r['tablas']['nucleus_data']==2
    with sqlite3.connect(destino) as c:
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        claves=[x[0] for x in c.execute('SELECT key_value FROM nucleus_data')]
        assert len(set(claves))==2
        assert c.execute('SELECT COUNT(*) FROM ensayo_procedencia WHERE tabla=?',('nucleus_data',)).fetchone()[0]==2
        assert {x[0] for x in c.execute('SELECT p.nombre FROM nucleus_data d JOIN proyectos p ON d.proyecto_id=p.id')}=={'FLM - INTEGRATEL'}
    assert all(p.read_bytes()==originales[n] for n,p in paths.items())
