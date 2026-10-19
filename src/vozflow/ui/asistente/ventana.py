"""La ventana del asistente de primer uso (002, RP-007, RP-013).

Pasos con Atrás, Siguiente y Saltear.

No sabe qué hace cada paso: solo los recorre. Al terminar o saltear guarda ``asistente.hecho`` para
no volver a aparecer, y se puede reabrir desde «General → Repetir el asistente».
"""

from collections.abc import Callable, Sequence

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.ui.asistente.base import PasoDelAsistente
from vozflow.ui.logo import logo


def debe_abrirse(ajustes: AjustesRepo) -> bool:
    """El asistente se abre solo la primera vez: mientras no esté hecho ni salteado."""
    return not bool(ajustes.obtener("asistente.hecho"))


class VentanaAsistente(QDialog):
    def __init__(
        self,
        pasos: Sequence[PasoDelAsistente] | Callable[[], Sequence[PasoDelAsistente]],
        ajustes: AjustesRepo,
        al_terminar: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__()
        self._fabrica = pasos if callable(pasos) else None
        self._pasos: list[PasoDelAsistente] = [] if callable(pasos) else list(pasos)
        self._ajustes = ajustes
        self._al_terminar = al_terminar
        self._actual = -1  # todavía no se mostró ningún paso
        self._avisado = False
        self.setWindowTitle("Bienvenida a vozflow")
        self.setWindowIcon(logo())
        self.resize(560, 460)
        self._titulo = QLabel()
        self._titulo.setObjectName("titulo")
        self._pila = QStackedWidget()
        for paso in self._pasos:
            self._agregar(paso)
        self.boton_atras = QPushButton("Atrás")
        self.boton_saltear = QPushButton("Saltear")
        self.boton_siguiente = QPushButton("Siguiente")
        self.boton_siguiente.setProperty("principal", True)
        self.boton_atras.clicked.connect(lambda _=False: self._atras())
        self.boton_saltear.clicked.connect(lambda _=False: self._terminar())
        self.boton_siguiente.clicked.connect(lambda _=False: self._siguiente())
        botones = QHBoxLayout()
        botones.addWidget(self.boton_saltear)
        botones.addStretch()
        botones.addWidget(self.boton_atras)
        botones.addWidget(self.boton_siguiente)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(28, 24, 28, 20)
        columna.addWidget(self._titulo)
        columna.addWidget(self._pila, 1)
        columna.addLayout(botones)

    # ---- interfaz pública ----

    def abrir(self) -> None:
        """Muestra el asistente desde el primer paso (también para repetirlo)."""
        self._avisado = False
        if self._fabrica is not None:
            self._rearmar(self._fabrica())
        if not self._pasos:
            self._terminar()
            return
        self._actual = -1
        self._ir_a(0)
        self.show()
        self.raise_()
        self.activateWindow()

    def titulo_del_paso(self) -> str:
        return self._titulo.text()

    def paso_actual(self) -> int:
        return self._actual

    def actualizar_botones(self) -> None:
        if not self._pasos or self._actual < 0:
            return
        paso = self._pasos[self._actual]
        ultimo = self._actual == len(self._pasos) - 1
        self.boton_atras.setEnabled(self._actual > 0)
        self.boton_siguiente.setText("Terminar" if ultimo else "Siguiente")
        self.boton_siguiente.setEnabled(paso.puede_avanzar())

    # ---- armado de los pasos ----

    def _agregar(self, paso: PasoDelAsistente) -> None:
        self._pila.addWidget(paso)
        paso.cambio.connect(self.actualizar_botones)

    def _rearmar(self, pasos: Sequence[PasoDelAsistente]) -> None:
        """Suelta los pasos de la vez anterior y pone los nuevos (los permisos pueden cambiar)."""
        for viejo in self._pasos:
            self._pila.removeWidget(viejo)
            viejo.deleteLater()
        self._pasos = list(pasos)
        for paso in self._pasos:
            self._agregar(paso)

    # ---- recorrido ----

    def showEvent(self, evento) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().showEvent(evento)
        if self._actual < 0 and self._pasos:
            self._ir_a(0)

    def _ir_a(self, indice: int) -> None:
        if 0 <= self._actual < len(self._pasos):
            self._pasos[self._actual].al_salir()
        self._actual = indice
        self._pila.setCurrentIndex(indice)
        paso = self._pasos[indice]
        self._titulo.setText(f"Paso {indice + 1} de {len(self._pasos)}: {paso.TITULO}")
        paso.al_entrar()
        self.actualizar_botones()

    def _siguiente(self) -> None:
        if self._actual == len(self._pasos) - 1:
            self._terminar()
        else:
            self._ir_a(self._actual + 1)

    def _atras(self) -> None:
        if self._actual > 0:
            self._ir_a(self._actual - 1)

    def _terminar(self) -> None:
        """Terminar y saltear son lo mismo para el resto del programa: ya no vuelve a aparecer."""
        if 0 <= self._actual < len(self._pasos):
            self._pasos[self._actual].al_salir()
        self.hide()
        if self._avisado:
            return
        self._avisado = True
        self._ajustes.establecer("asistente.hecho", True)
        self._al_terminar()

    def closeEvent(self, evento: QCloseEvent) -> None:  # noqa: N802 (nombre de Qt)
        self._terminar()
        evento.accept()
