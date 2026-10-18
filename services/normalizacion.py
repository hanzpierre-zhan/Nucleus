"""Normalización compartida; no interpreta proyectos ni modifica documentos."""

import re
import unicodedata
from functools import lru_cache

# Patrón compilado una vez (evita la búsqueda en la caché interna de `re` en
# cada llamada) y resultado memoizado: la misma clave se normaliza miles de
# veces al recorrer filas y catálogos.
_PATRON_NO_ALNUM = re.compile(r"[^a-z0-9]")


@lru_cache(maxsize=8192)
def _normalizar_texto(texto):
    return _PATRON_NO_ALNUM.sub(
        "",
        "".join(
            c
            for c in unicodedata.normalize("NFKD", texto).lower()
            if not unicodedata.combining(c)
        ),
    )


def normalizar(valor):
    valor = valor or ""
    if not isinstance(valor, str):
        valor = str(valor)
    return _normalizar_texto(valor)


def primer_texto(*vals):
    for v in vals:
        v = str(v or "").strip()
        if v:
            return v
    return ""
