# -*- coding: utf-8 -*-
"""Arranque en frío y comprobación de que pandas no se carga hasta usarlo."""
import os
import sys
import time

sys.path.insert(0, r'C:\Mega\Proyect\Nucleus')
DB = os.path.join(os.environ['TEMP'], 'bench_nucleus.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'bench')
os.environ['FLASK_ENV'] = 'testing'

t = time.perf_counter()
from app import create_app  # noqa: E402
t_import = (time.perf_counter() - t) * 1000
t = time.perf_counter()
app = create_app()
t_create = (time.perf_counter() - t) * 1000
print(f'import app:   {t_import:8.0f} ms')
print(f'create_app(): {t_create:8.0f} ms')
print(f'cold total:   {t_import + t_create:8.0f} ms')
print('pandas cargado al arrancar:', 'pandas' in sys.modules)
print('PIL cargado al arrancar:   ', 'PIL' in sys.modules)

# El proxy debe funcionar igual que el módulo real.
import pandas as real  # noqa: E402
from perezoso import pd  # noqa: E402
import io  # noqa: E402
df = pd.read_csv(io.StringIO('a,b\n1,2\n3,4\n'), dtype=str)
print('pd.read_csv ->', df.to_dict('list'))
print('pd.DataFrame igual:', pd.DataFrame({'x': [1]}).to_dict('list') == real.DataFrame({'x': [1]}).to_dict('list'))
print('pd.to_datetime igual:', pd.to_datetime('2026-10-17') == real.to_datetime('2026-10-17'))
print('pd.isna/notna igual:', pd.isna(None) == real.isna(None), pd.notna(1) == real.notna(1))
print('pd.ExcelWriter igual:', pd.ExcelWriter is real.ExcelWriter)
print('pandas cargado tras usarlo:', 'pandas' in sys.modules)
