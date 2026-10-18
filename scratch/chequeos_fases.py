# -*- coding: utf-8 -*-
"""Comprobaciones previas a las fases 3-7: qué hay disponible y qué es
determinista, para no añadir pruebas que fallen o que sean frágiles."""
import importlib.util as u
import io
import os
import sys

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + DB.replace('\\', '/'))
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

print('== librerias disponibles ==')
for nombre in ('playwright', 'pytest_cov', 'freezegun', 'responses', 'moto', 'pytest_mock'):
    print('  %-14s %s' % (nombre, 'SI' if u.find_spec(nombre) else 'no'))

print('== openpyxl: ¿bytes deterministas? ==')


def generar():
    import openpyxl
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(['a', 'b'])
    hoja.append(['1', '2'])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


print('  dos generaciones iguales:', generar() == generar())

print('== rutas GET sin parametros (candidatas al barrido) ==')
from app import create_app  # noqa: E402

app = create_app()
rutas = sorted({str(r) for r in app.url_map.iter_rules()
                if 'GET' in r.methods and '<' not in str(r)
                and not str(r).startswith(('/static', '/logout'))})
print('  total:', len(rutas))
for ruta in rutas:
    print('   ', ruta)
