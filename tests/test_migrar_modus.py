import json

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text, create_engine, select

from scripts.migrar_modus import importar, remapear_adjuntos
from scripts.plan_migracion_modus import aplicar, construir


def base(path, origen=False):
    engine = create_engine('sqlite:///' + str(path))
    m = MetaData()
    p = Table('proyectos', m, Column('id', Integer, primary_key=True),
              Column('nombre', String, unique=True))
    d = Table('nucleus_data', m, Column('id', Integer, primary_key=True),
              Column('proyecto_id', ForeignKey('proyectos.id')),
              Column('key_value', String), Column('data_json', Text))
    m.create_all(engine)
    with engine.begin() as c:
        c.execute(p.insert(), [{'id': 1 if origen else 11, 'nombre': 'Dataper'},
                               {'id': 2 if origen else 12, 'nombre': 'FLM - INTEGRATEL'}])
        c.execute(d.insert().values(id=1, proyecto_id=1 if origen else 11,
            key_value='persona', data_json=json.dumps({'DOCUMENTO': '123',
                'TECNICO': 'Origen' if origen else 'Actual'})))
        if origen:
            c.execute(d.insert().values(id=2, proyecto_id=2, key_value='WO-1',
                data_json=json.dumps({'foto': '/api/evidencia/foto/2/WO-1/inicio.jpg'})))
    return engine, d


def test_conserva_personal_remapea_y_repite_sin_duplicar(tmp_path):
    src, _ = base(tmp_path / 'origen.db', True)
    dst, tabla = base(tmp_path / 'destino.db')
    importar(src, dst)
    importar(src, dst)
    with dst.connect() as c:
        rows = c.execute(select(tabla).order_by(tabla.c.id)).mappings().all()
    assert len(rows) == 2
    assert json.loads(rows[0]['data_json'])['TECNICO'] == 'Actual'
    assert rows[1]['proyecto_id'] == 12
    assert '/foto/12/' in rows[1]['data_json']


def test_conflicto_revierte_toda_la_carga(tmp_path):
    src, _ = base(tmp_path / 'origen.db', True)
    dst, tabla = base(tmp_path / 'destino.db')
    with dst.begin() as c:
        c.execute(tabla.insert().values(id=2, proyecto_id=12,
            key_value='WO-1', data_json='{"conservar":true}'))
    with pytest.raises(ValueError, match='conflictivo'):
        importar(src, dst)
    with dst.connect() as c:
        assert len(c.execute(select(tabla)).all()) == 2
        assert c.scalar(select(tabla.c.data_json).where(tabla.c.id == 2)) == '{"conservar":true}'


def test_no_modifica_textos_y_remapea_adjuntos_serializados():
    d = {'texto': 'proyecto 2', 'fotos': '["/api/evidencia/foto/2/WO/a.jpg"]',
         'correo': '/api/cotizacion/correo/9/COT/a.pdf'}
    r = remapear_adjuntos(d, {2: 12, 9: 19})
    assert r['texto'] == d['texto']
    assert '/foto/12/' in r['fotos']
    assert '/correo/19/' in r['correo']
    assert d['correo'].startswith('/api/cotizacion/correo/9/')


def test_plan_por_lotes_reproduce_ensayo_y_rechaza_destino_cambiado(tmp_path):
    src, _ = base(tmp_path / 'origen.db', True)
    ensayo, _ = base(tmp_path / 'ensayo.db')
    destino, tabla = base(tmp_path / 'destino.db')
    importar(src, ensayo)
    plan = construir(destino, ensayo)
    resultado = aplicar(plan, destino)
    assert resultado['nucleus_data']['insertados'] == 1
    with destino.connect() as c:
        assert len(c.execute(select(tabla)).all()) == 2
    with pytest.raises(ValueError, match='Destino cambiado'):
        aplicar(plan, destino)


def test_plan_no_sobreescribe_cambios_posteriores_al_respaldo(tmp_path):
    src, _ = base(tmp_path / 'origen.db', True)
    ensayo, _ = base(tmp_path / 'ensayo.db')
    destino, tabla = base(tmp_path / 'destino.db')
    importar(src, ensayo)
    plan = construir(destino, ensayo)
    with destino.begin() as c:
        c.execute(tabla.update().where(tabla.c.id == 1).values(data_json='{"nuevo":true}'))
    with pytest.raises(ValueError, match='Destino cambiado'):
        aplicar(plan, destino)
    with destino.connect() as c:
        assert c.scalar(select(tabla.c.data_json).where(tabla.c.id == 1)) == '{"nuevo":true}'
