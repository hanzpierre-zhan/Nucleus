import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys


def test_importar_wsgi_no_carga_la_app_y_el_primer_request_la_inicializa(monkeypatch):
    path=Path(__file__).resolve().parents[1]/'wsgi.py'
    spec=importlib.util.spec_from_file_location('nucleus_wsgi_test',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._application is None
    calls=[]
    def app(environ,start_response):
        calls.append(environ['PATH_INFO'])
        start_response('200 OK',[])
        return [b'OK']
    monkeypatch.setitem(sys.modules,'app',SimpleNamespace(app=app))
    assert module.application({'PATH_INFO':'/healthz'},lambda *args:None)==[b'OK']
    assert module._application is app
    assert module.application({'PATH_INFO':'/otra'},lambda *args:None)==[b'OK']
    assert calls==['/healthz','/otra']
