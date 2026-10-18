# -*- coding: utf-8 -*-
"""El proxy perezoso de pandas debe comportarse como el módulo real.

`from perezoso import pd` difiere la carga de pandas (~0.4 s de arranque en
frío); estos atajos comprueban que los usos reales del proyecto devuelven
exactamente los mismos objetos que `import pandas as pd`.
"""
import importlib


def test_pd_perezoso_devuelve_el_modulo_real():
    from perezoso import pd
    real = importlib.import_module('pandas')
    assert pd.DataFrame is real.DataFrame
    assert pd.read_csv is real.read_csv
    assert pd.read_excel is real.read_excel
    assert pd.to_datetime is real.to_datetime
    assert pd.to_numeric is real.to_numeric
    assert pd.isna is real.isna
    assert pd.notna is real.notna
    assert pd.ExcelWriter is real.ExcelWriter


def test_pd_perezoso_es_utilizable():
    import io
    from perezoso import pd
    df = pd.read_csv(io.StringIO('a,b\n1,2\n'), dtype=str)
    assert df.to_dict('list') == {'a': ['1'], 'b': ['2']}
    assert pd.to_datetime('2026-10-17').year == 2026
