import hashlib,json,sqlite3
from pathlib import Path
from db import db
from scripts.auditar_integridad import audit


def copia(app,tmp_path):
    destino=tmp_path/'auditoria.db'
    with app.app_context():
        fuente=Path(db.engine.url.database)
        with sqlite3.connect('file:'+fuente.resolve().as_posix()+'?mode=ro',uri=True) as src,sqlite3.connect(destino) as dst:src.backup(dst)
    return destino


def test_auditoria_no_modifica_y_no_expone_valores(app,tmp_path):
    base=copia(app,tmp_path);root=tmp_path/'codigo';root.mkdir()
    antes=hashlib.sha256(base.read_bytes()).hexdigest()
    resultado=audit(base,root)
    assert resultado['integridad']==['ok']
    assert hashlib.sha256(base.read_bytes()).hexdigest()==antes
    assert resultado['limpieza_segura']==[]
    assert 'zeno123' not in json.dumps(resultado)
    assert all('columnas' in t for t in resultado['tablas'].values())


def test_auditoria_detecta_fk_y_json_sin_reparar_a_ciegas(app,tmp_path):
    base=copia(app,tmp_path);root=tmp_path/'codigo';root.mkdir()
    with sqlite3.connect(base) as c:
        c.execute('INSERT INTO nucleus_data(proyecto_id,key_value,data_json) VALUES(?,?,?)',(999999,'PRUEBA-ERROR','NO ES JSON'))
    resultado=audit(base,root)
    assert len(resultado['referencias_rotas'])>=1
    assert any(e['tabla']=='nucleus_data' for e in resultado['errores_json'])
    with sqlite3.connect(base) as c:assert c.execute('SELECT COUNT(*) FROM nucleus_data WHERE proyecto_id=999999').fetchone()[0]==1


def test_columna_vacia_de_formulario_no_es_fantasma(app,tmp_path):
    base=copia(app,tmp_path);root=tmp_path/'codigo';root.mkdir()
    field=''.join(['Unnamed',': ',str(77)])
    with sqlite3.connect(base) as c:
        pid=c.execute("SELECT id FROM proyectos WHERE nombre='Dataper'").fetchone()[0]
        c.execute("UPDATE app_config SET valor=? WHERE proyecto_id=? AND clave='app_schema'",(json.dumps([field,'CAMPO FUTURO']),pid))
        c.execute("UPDATE app_config SET valor=? WHERE proyecto_id=? AND clave='manual_columns'",(json.dumps([{'nombre':'CAMPO FUTURO','tipo':'texto'}]),pid))
    resultado=audit(base,root)
    assert any(x['campo']==field for x in resultado['limpieza_segura'])
    assert not any(x['campo']=='CAMPO FUTURO' for x in resultado['limpieza_segura'])
