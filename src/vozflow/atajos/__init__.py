"""Atajos de teclado globales: «alternar» con un atajo de GNOME y «mantener» leyendo el teclado."""

from vozflow.atajos.compuesta import EscuchaCompuesta
from vozflow.atajos.evdev import EscuchaEvdev
from vozflow.atajos.gnome import EscuchaDeGnome
from vozflow.atajos.puerto import AccionDeAtajo


def crear_escucha() -> EscuchaCompuesta:
    """La línea base observada funcionando en este escritorio (research.md, sección 11).

    Cada acción tiene una lista de técnicas en orden de preferencia; si una falla, se prueba la
    siguiente. El portal ``GlobalShortcuts`` se sumará aquí solo si la comprobación A lo prueba
    mejor que ``evdev``.
    """
    por_evdev = [EscuchaEvdev]  # la misma lista: las de mantener leen el teclado juntas
    return EscuchaCompuesta(
        {
            AccionDeAtajo.ALTERNAR: [EscuchaDeGnome],
            AccionDeAtajo.MANTENER: por_evdev,
            AccionDeAtajo.TRADUCIR: por_evdev,
            AccionDeAtajo.MEJORAR: por_evdev,
        }
    )
