"""Paso de arrancar con la sesión del asistente (002, RP-012, RP-014): se ofrece, no se impone."""

from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QVBoxLayout

from vozflow.ui.asistente.base import PasoDelAsistente
from vozflow.ui.componentes import FilaDeAjuste, Interruptor
from vozflow.ui.textos import ayuda_de, texto_de


class PasoArranque(PasoDelAsistente):
    TITULO = "Arrancar con tu computadora"

    def __init__(self, leer: Callable[[], bool], fijar: Callable[[bool], None]) -> None:
        super().__init__()
        self._leer = leer
        self._fijar = fijar
        self.interruptor = Interruptor()
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        columna = QVBoxLayout(self)
        columna.addWidget(
            FilaDeAjuste(texto_de("autoinicio").titulo, ayuda_de("autoinicio"), self.interruptor)
        )
        columna.addWidget(self.aviso)
        columna.addStretch()
        self.interruptor.setChecked(leer())
        self.interruptor.toggled.connect(self._cambio)

    def puede_avanzar(self) -> bool:
        return True

    def al_entrar(self) -> None:
        self.interruptor.blockSignals(True)
        self.interruptor.setChecked(self._leer())
        self.interruptor.blockSignals(False)

    def _cambio(self, activo: bool) -> None:
        try:
            self._fijar(activo)
        except (OSError, ValueError) as error:  # FileExistsError es un OSError
            self.interruptor.blockSignals(True)
            self.interruptor.setChecked(not activo)
            self.interruptor.blockSignals(False)
            self.aviso.setText(str(error))
            return
        self.aviso.setText(
            "vozflow arrancará en segundo plano con la sesión."
            if activo
            else "vozflow ya no arranca con la sesión."
        )
