"""La pista para el motor a partir del diccionario personal (RF-019)."""

from collections.abc import Sequence

from vozflow.dominio.claves import normalizar_clave

TOPE_POR_DEFECTO = 400
"""Caracteres. El motor solo atiende unas 200 unidades de la pista; más no sirve."""
_SEPARADOR = ", "


def construir_pista(palabras: Sequence[str], tope: int = TOPE_POR_DEFECTO) -> str | None:
    """``palabras`` va de la más vieja a la más reciente.

    Si no caben todas dentro de ``tope`` caracteres, entran primero las más recientes; una
    palabra que sola no entra se salta. Sin ninguna palabra que entre, devuelve ``None``.
    """
    vistas: set[str] = set()
    unicas: list[str] = []
    for palabra in palabras:
        limpia = palabra.strip()
        clave = normalizar_clave(limpia)
        if clave and clave not in vistas:
            vistas.add(clave)
            unicas.append(limpia)
    elegidas: list[str] = []
    largo = 0
    for palabra in reversed(unicas):
        costo = len(palabra) + (len(_SEPARADOR) if elegidas else 0)
        if largo + costo <= tope:
            elegidas.append(palabra)
            largo += costo
    if not elegidas:
        return None
    return _SEPARADOR.join(reversed(elegidas))
