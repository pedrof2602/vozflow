"""¿La tecla elegida existe en el teclado de la persona? (002, RP-009).

Hay teclados compactos sin Ctrl derecho o sin teclas de función: elegir una que no existe dejaría el
dictado sin forma de usarse. Esto lo detecta con lo que informa el teclado y propone otra.
"""

import logging
from collections.abc import Callable, Iterable

from vozflow.atajos.evdev import (
    _GRUPOS,
    DispositivoDeEntrada,
    ListadorDeTeclados,
    es_teclado_real,
    parsear_atajo,
)

_registro = logging.getLogger(__name__)

CANDIDATAS = ("RightCtrl", "RightAlt", "F9", "F10", "Pause", "ScrollLock")
"""En orden de comodidad para mantener apretada mientras se habla."""


def teclas_del_teclado(
    listar: Callable[[], list[DispositivoDeEntrada]] | None = None,
) -> set[int]:
    """Las teclas que tienen los teclados reales conectados; vacío si no se pueden leer."""
    try:
        teclados = (listar or ListadorDeTeclados())()
    except Exception:
        _registro.debug("No se pudo leer qué teclas tiene el teclado", exc_info=True)
        return set()
    teclas: set[int] = set()
    for teclado in teclados:
        propias = teclado.teclas()
        if es_teclado_real(teclado.nombre, propias):
            teclas |= propias
    return teclas


def atajo_disponible(atajo: str, teclas: set[int]) -> bool:
    """Si el teclado tiene la tecla principal y algún lado de cada modificador del atajo.

    Si no se conocen las teclas (no se pudo leer el teclado) no se bloquea a nadie.
    """
    try:
        combinacion = parsear_atajo(atajo)
    except ValueError:
        return False
    if not teclas:
        return True
    if combinacion.tecla not in teclas:
        return False
    return all(any(c in teclas for c in _GRUPOS[grupo]) for grupo in combinacion.modificadores)


def _forma(atajo: str) -> tuple[int, frozenset[str]] | None:
    try:
        combinacion = parsear_atajo(atajo)
    except ValueError:
        return None
    return combinacion.tecla, combinacion.modificadores


def proponer_tecla(teclas: set[int], excluir: Iterable[str] = ()) -> str | None:
    """La primera tecla cómoda que el teclado tenga y que no esté en uso en otra función."""
    ocupadas = {f for f in (_forma(e) for e in excluir) if f is not None}
    for candidata in CANDIDATAS:
        if _forma(candidata) in ocupadas:
            continue
        if atajo_disponible(candidata, teclas):
            return candidata
    return None
