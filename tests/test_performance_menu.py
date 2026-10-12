from services.utilidades import get_menu_proyectos
from db import db

def test_permisos_se_reutilizan_solo_en_la_misma_peticion(app,monkeypatch):
    import services.utilidades as util
    calls=[]
    original=util._get_menu_proyectos
    def counted(uid,rol):
        calls.append((uid,rol));return original(uid,rol)
    monkeypatch.setattr(util,'_get_menu_proyectos',counted)
    with app.test_request_context():
        first=get_menu_proyectos(1,'zeno');expected=[p.id for p in first]
        first.clear()
        assert [p.id for p in get_menu_proyectos(1,'zeno')]==expected
        assert len(calls)==1
        get_menu_proyectos(2,'gestor');assert len(calls)==2
        db.session.commit()
        get_menu_proyectos(1,'zeno');assert len(calls)==3
    with app.test_request_context():
        get_menu_proyectos(1,'zeno');assert len(calls)==4
