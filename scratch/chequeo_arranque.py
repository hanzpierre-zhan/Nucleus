# -*- coding: utf-8 -*-
"""Comprobación de arranque: tiempo y librerías cargadas de más."""
import os
import sys
import time

raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, raiz)
temp = os.environ.get('TEMP') or os.environ.get('TMP') or '.'
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(temp, 'chequeo_arranque.db').replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'chequeo')
os.environ.setdefault('FLASK_ENV', 'testing')

pesadas = ('pandas', 'numpy', 'openpyxl', 'boto3', 'reportlab', 'docx')

inicio = time.perf_counter()
import app as modulo_app  # noqa: E402

print('crear la app: %.0f ms' % ((time.perf_counter() - inicio) * 1000))
print('app lista:', modulo_app.app is not None)
for nombre in pesadas:
    cargada = nombre in sys.modules
    print('  %-10s cargada al arrancar: %s' % (nombre, 'SI' if cargada else 'no'))
print('modulos totales cargados:', len(sys.modules))
