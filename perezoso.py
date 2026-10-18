# -*- coding: utf-8 -*-
"""Carga diferida de librerías pesadas.

`pandas` tarda ~0.4 s en importarse y, en la instancia gratuita de Render, ese
tiempo se paga en cada arranque en frío (el servicio se duerme al quedar
inactivo). Con este objeto el módulo real se importa la PRIMERA vez que se usa,
así que las pantallas que no leen Excel/CSV arrancan antes.

Uso:
    from perezoso import pd
    df = pd.read_excel(...)   # aquí se importa pandas (una sola vez)
"""

_MODULOS = {}


class _ModuloPerezoso:
    """Sustituto de un módulo: lo importa en el primer acceso a un atributo.

    Se comporta como el módulo de verdad para cualquier acceso (`pd.read_csv`,
    `pd.DataFrame`, `pd.to_datetime`, ...) y no cambia el código que lo usa.
    """

    def __init__(self, nombre):
        self._nombre = nombre

    def __getattr__(self, atributo):
        import importlib
        modulo = _MODULOS.get(self._nombre)
        if modulo is None:
            modulo = _MODULOS[self._nombre] = importlib.import_module(self._nombre)
        return getattr(modulo, atributo)

    def __repr__(self):
        return '<modulo perezoso %r>' % self._nombre


pd = _ModuloPerezoso('pandas')
