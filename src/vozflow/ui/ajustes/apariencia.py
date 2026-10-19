"""Página de apariencia de los ajustes: tema automático, claro u oscuro."""

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.ui.componentes import Chips, FilaDeAjuste

_OPCIONES = (
    ("Automático (como el sistema)", "auto"),
    ("Claro", "claro"),
    ("Oscuro", "oscuro"),
)


class PaginaApariencia(QWidget):
    def __init__(self, ajustes: AjustesRepo, aplicar_tema: Callable[[str], None]) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._aplicar_tema = aplicar_tema
        self.selector = Chips()
        for texto, modo in _OPCIONES:
            self.selector.addItem(texto, modo)
        self.selector.setCurrentIndex(self.selector.findData(ajustes.obtener("interfaz.tema")))
        self.selector.currentIndexChanged.connect(lambda _: self._elegido())
        columna = QVBoxLayout(self)
        columna.addWidget(
            FilaDeAjuste(
                "Tema", "Con «Automático» sigue al color del sistema y cambia solo.", self.selector
            )
        )
        columna.addStretch()

    def _elegido(self) -> None:
        modo = str(self.selector.currentData())
        self._ajustes.establecer("interfaz.tema", modo)
        self._aplicar_tema(modo)
