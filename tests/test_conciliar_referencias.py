import json,sqlite3
from scripts.conciliar_referencias import planificar,aplicar


def base(path):
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE proyectos(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE)')
        c.execute('CREATE TABLE nucleus_data(id INTEGER PRIMARY KEY,proyecto_id INTEGER REFERENCES proyectos(id),key_value TEXT,data_json TEXT,UNIQUE(proyecto_id,key_value))')
        c.executemany('INSERT INTO proyectos VALUES(?,?)',[(1,'Rendicion'),(2,'FLM - INTEGRATEL'),(3,'Generadores'),(4,'Combustible')])
    return path


def insertar(path,pid,key,datos):
    with sqlite3.connect(path) as c:c.execute('INSERT INTO nucleus_data(proyecto_id,key_value,data_json) VALUES(?,?,?)',(pid,key,json.dumps(datos)))


def test_conciliacion_aditiva_exacta_idempotente_y_qr_real(tmp_path):
    activa=base(tmp_path/'activa.db');fuente=base(tmp_path/'fuente.db')
    insertar(activa,1,'R1',{'Nombre del proyecto':'Integratel','Número CM / PM / PLM':'CM-001'})
    insertar(activa,3,'ID-INTERNO-1',{'QR ASIGNADO':'GEN-1'})
    insertar(activa,4,'C1',{'QR ASIGNADO':'GEN-1'})
    insertar(fuente,2,'CM-001',{'Task Id':'CM-001','OBSERVACION':'Histórico original'})
    plan=planificar(activa,[fuente]);assert len(plan['insertar'])==1 and plan['insertar'][0]['modulo']=='FLM - INTEGRATEL'
    assert not any(p['tipo']=='QR' for p in plan['pendientes'])
    cambios=aplicar(activa,plan);assert len(cambios)==1
    assert len(aplicar(activa,plan))==0
    assert planificar(activa,[fuente])['insertar']==[]
    with sqlite3.connect(activa) as c:
        assert c.execute('select count(*) from conciliacion_origen').fetchone()[0]==1
        d=json.loads(c.execute("select data_json from nucleus_data where key_value='CM-001'").fetchone()[0]);assert d['OBSERVACION']=='Histórico original'
        assert c.execute('pragma foreign_key_check').fetchall()==[]


def test_fuentes_con_conflicto_no_se_eligen_a_ciegas(tmp_path):
    activa=base(tmp_path/'activa.db');a=base(tmp_path/'a.db');b=base(tmp_path/'b.db')
    insertar(activa,1,'R1',{'Nombre del proyecto':'Integratel','Número CM / PM / PLM':'CM-001'})
    insertar(a,2,'CM-001',{'ESTADO':'A'});insertar(b,2,'CM-001',{'ESTADO':'B'})
    plan=planificar(activa,[a,b]);assert plan['insertar']==[]
    assert plan['pendientes'][0]['motivo']=='fuentes_en_conflicto'


def test_registro_activo_no_se_sobrescribe(tmp_path):
    activa=base(tmp_path/'activa.db');a=base(tmp_path/'a.db')
    insertar(activa,1,'R1',{'Nombre del proyecto':'Integratel','Número CM / PM / PLM':'CM-001'})
    insertar(activa,2,'CM-001',{'ESTADO':'ACTUAL'});insertar(a,2,'CM-001',{'ESTADO':'ANTERIOR'})
    plan=planificar(activa,[a]);assert plan['insertar']==[]
    with sqlite3.connect(activa) as c:assert json.loads(c.execute("select data_json from nucleus_data where key_value='CM-001'").fetchone()[0])['ESTADO']=='ACTUAL'
