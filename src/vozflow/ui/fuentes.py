"""La tipografía de la interfaz.

La guía de OpenWhispr usa una sans humanista tipo Inter. Se toma la primera que esté instalada;
*Adwaita Sans* (la fuente de GNOME, derivada de Inter) ya viene en Fedora, así que no se
empaqueta ninguna fuente.
"""

from collections.abc import Iterable

FAMILIAS_PREFERIDAS = ("Inter", "Adwaita Sans", "Noto Sans", "Cantarell")
GENERICA = "sans-serif"


def elegir_familia(disponibles: Iterable[str]) -> str:
    """La primera de ``FAMILIAS_PREFERIDAS`` que figure en ``disponibles`` (sin mayúsculas)."""
    existentes = {nombre.casefold() for nombre in disponibles}
    for preferida in FAMILIAS_PREFERIDAS:
        if preferida.casefold() in existentes:
            return preferida
    return GENERICA


def familia_del_sistema() -> str:
    """La familia a usar según las fuentes que Qt ve instaladas (necesita una ``QApplication``)."""
    from PySide6.QtGui import QFontDatabase

    return elegir_familia(QFontDatabase.families())
