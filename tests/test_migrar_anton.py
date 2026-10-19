import json

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text, create_engine, select

from scripts.migrar_anton import aplicar_archivos, importar, tablas_procedencia


def test_rutas_conflictivas_conservan_carpeta_wo_y_remapean_proyecto():
    original = {'foto': '/api/evidencia/foto/2/CM-1/pex_0.jpg', 'texto': 'CM-1/pex_0.jpg'}
    result = aplicar_archivos(original, {2: 20}, {'CM-1/pex_0.jpg': 'CM-1/pex_0_anton_abc.jpg'})
    assert result == {'foto': '/api/evidencia/foto/20/CM-1/pex_0_anton_abc.jpg', 'texto': original['texto']}
    assert original['foto'].endswith('/pex_0.jpg')


def test_procedencia_admite_descripcion_de_conservacion():
    journal, _ = tablas_procedencia(MetaData())
    assert journal.c.accion.type.length >= len('nucleus_conservado_version_anton_archivada')


def test_importacion_separa_personal_por_proyecto_remapea_historial_y_no_duplica(tmp_path):
    def base(name):
        engine = create_engine('sqlite:///' + (tmp_path / name).as_posix())
        meta = MetaData()
        Table('proyectos', meta, Column('id', Integer, primary_key=True), Column('nombre', String, unique=True))
        Table('nucleus_data', meta, Column('id', Integer, primary_key=True),
              Column('proyecto_id', ForeignKey('proyectos.id')), Column('key_value', String), Column('data_json', Text))
        Table('cotizaciones', meta, Column('id', Integer, primary_key=True),
              Column('proyecto_id', ForeignKey('proyectos.id')), Column('key_value', String),
              Column('numero', String), Column('formato', String))
        Table('historial_cambios', meta, Column('id', Integer, primary_key=True),
              Column('proyecto_id', ForeignKey('proyectos.id')), Column('key_value', String), Column('username', String))
        meta.create_all(engine)
        return engine, meta.tables

    source, s = base('source.db')
    target, t = base('target.db')
    with source.begin() as c:
        c.execute(s['proyectos'].insert(), [{'id': 1, 'nombre': 'Dataper'}, {'id': 2, 'nombre': 'PEXT'}, {'id': 3, 'nombre': 'Cotizaciones'}])
        c.execute(s['nucleus_data'].insert(), [
            {'id': 1, 'proyecto_id': 1, 'key_value': '123', 'data_json': json.dumps({'DOCUMENTO': '123', 'PROYECTO': 'PEXT'})},
            {'id': 2, 'proyecto_id': 3, 'key_value': 'HW-001', 'data_json': json.dumps({'ESTADO COTIZACION': 'Pendiente de Aprobacion', 'GENERADA': '1', 'ITEMS_JSON': '[]'})}])
        c.execute(s['historial_cambios'].insert(), {'id': 1, 'proyecto_id': 3, 'key_value': 'HW-001', 'username': 'gestora'})
    original = json.dumps({'DOCUMENTO': '123', 'PROYECTO': 'FLM - ENTEL'})
    with target.begin() as c:
        c.execute(t['proyectos'].insert(), [{'id': 10, 'nombre': 'Dataper'}, {'id': 20, 'nombre': 'FLM - PEXT'}, {'id': 30, 'nombre': 'Cotizaciones'}])
        c.execute(t['nucleus_data'].insert(), {'id': 10, 'proyecto_id': 10, 'key_value': '123', 'data_json': original})
    importar(source, target)
    with target.connect() as c:
        rows = list(c.execute(select(t['nucleus_data']).order_by(t['nucleus_data'].c.id)).mappings())
        assert len(rows) == 3 and rows[0]['data_json'] == original
        assert rows[1]['key_value'] != '123'
        assert json.loads(rows[1]['data_json'])['PROYECTO'] == 'FLM - PEXT'
        history = c.execute(select(t['historial_cambios'])).mappings().one()
        assert history['key_value'] == 'PX-001' and history['proyecto_id'] == 30
    repeat = importar(source, target)
    assert all(k.endswith(':ya_migrado') for k in repeat['resumen'])
