# -*- coding: utf-8 -*-
"""La app no debe romperse cuando falla la red o falta configuración externa.

Capa 1 de la estrategia (docs/estrategia_testing.md §4.9). Aquí los fallos
"raros" se provocan a propósito (con `monkeypatch` del propio Python, sin
librerías extra) y se exige una respuesta controlada en lugar de una excepción.

Son pruebas de caracterización: no cambian nada del código, solo fijan lo que ya
hace hoy para que no se degrade sin darnos cuenta.
"""
import urllib.error
import urllib.request

from db import db
from models import AppConfig, Proyecto


def test_descarga_de_foto_informa_fallo_en_vez_de_romperse(app, monkeypatch):
    """`_bajar_foto_form` devuelve (None, None) si la descarga falla."""
    def _sin_red(*_args, **_kwargs):
        raise urllib.error.URLError('sin red')

    monkeypatch.setattr(urllib.request, 'urlopen', _sin_red)
    with app.app_context():
        from blueprints.rendicion import _bajar_foto_form
        assert _bajar_foto_form('https://ejemplo.invalido/foto.jpg') == (None, None)


def test_evidencia_usa_b2_es_falso_sin_configuracion(app):
    """Sin credenciales de B2, la app usa la carpeta local (no intenta la nube)."""
    with app.app_context():
        from services.apoyo import evidencia_usa_b2
        assert evidencia_usa_b2() is False


def test_sincronizacion_de_rendicion_informa_fallo_de_red(app, auth_client, monkeypatch):
    """Si no se puede descargar el CSV del formulario, responde 502 con un
    mensaje claro en lugar de propagar la excepción."""
    with app.app_context():
        proyecto = Proyecto.query.filter_by(nombre='Rendicion').one()
        config = AppConfig.query.filter_by(proyecto_id=proyecto.id,
                                          clave='rendicion_csv_url').first()
        previo = config.valor if config else None
        if config is None:
            config = AppConfig(proyecto_id=proyecto.id, clave='rendicion_csv_url',
                               valor='https://ejemplo.invalido/rendicion.csv')
            db.session.add(config)
        else:
            config.valor = 'https://ejemplo.invalido/rendicion.csv'
        db.session.commit()
        pid = proyecto.id
    try:
        def _sin_red(*_args, **_kwargs):
            raise urllib.error.URLError('sin red')

        monkeypatch.setattr(urllib.request, 'urlopen', _sin_red)
        auth_client.get('/switch_project/%s' % pid)
        respuesta = auth_client.get('/api/rendicion/sync')
        assert respuesta.status_code == 502
        assert 'error' in (respuesta.get_json() or {})
    finally:
        with app.app_context():
            config = AppConfig.query.filter_by(proyecto_id=pid,
                                              clave='rendicion_csv_url').first()
            if config is not None:
                if previo is None:
                    db.session.delete(config)
                else:
                    config.valor = previo
                db.session.commit()
