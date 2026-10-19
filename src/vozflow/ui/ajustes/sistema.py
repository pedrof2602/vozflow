"""Página de sistema de los ajustes: arrancar vozflow en segundo plano al iniciar la sesión."""

from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QVBoxLayout

from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.componentes import FilaDeAjuste, Interruptor


class PaginaSistema(PaginaBase):
    def __init__(self, leer: Callable[[], bool], fijar: Callable[[bool], None]) -> None:
        super().__init__()
        self._fijar = fijar
        self.interruptor = Interruptor()
        self.interruptor.setChecked(leer())
        self.interruptor.toggled.connect(self._cambio)
        explicacion = QLabel(
            "Con esto prendido, vozflow arranca solo en segundo plano cada vez que iniciás "
            "la sesión y queda listo para dictar, sin que abras nada."
        )
        explicacion.setObjectName("descripcion")
        explicacion.setWordWrap(True)
        columna = QVBoxLayout(self)
        columna.addWidget(
            FilaDeAjuste(
                "Arrancar con la sesión",
                "Se activa o se apaga con un clic, sin reiniciar.",
                self.interruptor,
            )
        )
        columna.addWidget(explicacion)
        columna.addWidget(self._etiqueta_mensaje)
        columna.addStretch()

    def _cambio(self, activo: bool) -> None:
        try:
            self._fijar(activo)
        except (OSError, ValueError) as error:  # FileExistsError es un OSError
            self.interruptor.blockSignals(True)
            self.interruptor.setChecked(not activo)
            self.interruptor.blockSignals(False)
            self.avisar(str(error), error=True)
            return
        self.avisar(
            "vozflow arrancará en segundo plano con la sesión."
            if activo
            else "vozflow ya no arranca con la sesión.",
        )
