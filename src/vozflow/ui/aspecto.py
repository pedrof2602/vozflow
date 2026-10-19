"""Aplica a toda la aplicación el tema y la tipografía, y los cambia si el sistema cambia."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vozflow.ui.fuentes import familia_del_sistema
from vozflow.ui.logo import logo
from vozflow.ui.tema import (
    Paleta,
    establecer_paleta,
    hoja_de_estilos,
    paleta_del_sistema,
    preparar_recursos,
)


def esquema_del_sistema(app: QApplication) -> str | None:
    """``dark`` o ``light`` según el sistema; ``None`` si no lo informa."""
    esquema = app.styleHints().colorScheme()
    if esquema == Qt.ColorScheme.Dark:
        return "dark"
    if esquema == Qt.ColorScheme.Light:
        return "light"
    return None


class Aspecto:
    def __init__(self, app: QApplication, directorio_de_recursos: Path) -> None:
        self._app = app
        self._directorio = directorio_de_recursos
        self._oyentes: list[Callable[[Paleta], None]] = []
        self.fuente = "sans-serif"
        self.paleta = paleta_del_sistema(None)

    def al_cambiar(self, oyente: Callable[[Paleta], None]) -> None:
        self._oyentes.append(oyente)

    def aplicar(self, esquema: str | None) -> None:
        self.paleta = paleta_del_sistema(esquema)
        self.fuente = familia_del_sistema()
        establecer_paleta(self.paleta)
        recursos = preparar_recursos(self.paleta, self._directorio)
        self._app.setStyleSheet(hoja_de_estilos(self.paleta, self.fuente, recursos))
        self._app.setWindowIcon(logo())
        for oyente in self._oyentes:
            oyente(self.paleta)

    def seguir_al_sistema(self, esquema: Callable[[], str | None] | None = None) -> None:
        """Vuelve a aplicar el tema cada vez que el sistema cambia de claro a oscuro."""
        leer = esquema or (lambda: esquema_del_sistema(self._app))
        self._app.styleHints().colorSchemeChanged.connect(lambda *_: self.aplicar(leer()))
