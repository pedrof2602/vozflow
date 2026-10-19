"""Paso del micrófono del asistente (002, RP-008): elegirlo y ver que reacciona a la voz."""

import logging
from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout

from vozflow.audio.captura import Dispositivo, ErrorDeAudio
from vozflow.mensajes import explicar
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.ui.asistente.base import PasoDelAsistente
from vozflow.ui.componentes import MedidorDeNivel
from vozflow.ui.microfonos import llenar_combo_de_microfonos

_registro = logging.getLogger(__name__)
_CADA_MS = 60


class Medidor(Protocol):
    """Abre el micrófono solo para ver su volumen: no graba ni guarda nada."""

    def iniciar(self, dispositivo: str | int | None) -> None: ...
    def nivel(self) -> float: ...
    def detener(self) -> None: ...


class PasoMicrofono(PasoDelAsistente):
    TITULO = "Micrófono"

    def __init__(
        self,
        ajustes: AjustesRepo,
        listar: Callable[[], list[Dispositivo]],
        medidor: Medidor,
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._listar = listar
        self._medidor = medidor
        self._midiendo = False
        self._hay_microfonos = False
        self._error: ErrorDeAudio | None = None
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(lambda _: self._elegido())
        self.boton_buscar = QPushButton("Buscar de nuevo")
        self.boton_buscar.clicked.connect(lambda _=False: self._buscar_de_nuevo())
        self.indicador = MedidorDeNivel()
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setProperty("error", True)
        self._reloj = QTimer(self)
        self._reloj.setInterval(_CADA_MS)
        self._reloj.timeout.connect(self.actualizar_medidor)
        ayuda = QLabel(
            "Hablá como si estuvieras dictando: la barra tiene que moverse con tu voz. "
            "Si no se mueve, probá con otro micrófono."
        )
        ayuda.setWordWrap(True)
        columna = QVBoxLayout(self)
        columna.addWidget(ayuda)
        columna.addWidget(self.combo)
        columna.addWidget(self.indicador)
        columna.addWidget(self.aviso)
        columna.addWidget(self.boton_buscar)
        columna.addStretch()

    # ---- el paso ----

    def puede_avanzar(self) -> bool:
        return self._hay_microfonos and self._error is None

    def al_entrar(self) -> None:
        self._cargar()

    def al_salir(self) -> None:
        self._reloj.stop()
        self._parar()

    def nivel_mostrado(self) -> float:
        return self.indicador.valor()

    def actualizar_medidor(self) -> None:
        if self._midiendo:
            self.indicador.establecer(self._medidor.nivel())

    # ---- internos ----

    def _cargar(self) -> None:
        self.combo.blockSignals(True)
        guardado = str(self._ajustes.obtener("audio.dispositivo"))
        cantidad = llenar_combo_de_microfonos(self.combo, guardado, self._listar)
        self.combo.blockSignals(False)
        self._hay_microfonos = cantidad > 0
        self._error = None
        self.aviso.clear()
        if not self._hay_microfonos:
            self._explicar("sin_microfono")
            return
        self._empezar_a_medir()

    def _empezar_a_medir(self) -> None:
        self._parar()
        dispositivo = self.combo.currentData() or None
        try:
            self._medidor.iniciar(dispositivo)
        except ErrorDeAudio as error:
            _registro.warning("No se pudo abrir el micrófono en el asistente: %s", error)
            self._error = error
            self._explicar(error.codigo)
            return
        self._midiendo = True
        self._reloj.start()

    def _parar(self) -> None:
        if self._midiendo:
            self._medidor.detener()
        self._midiendo = False
        self.indicador.establecer(0.0)

    def _elegido(self) -> None:
        self._ajustes.establecer("audio.dispositivo", self.combo.currentData() or "")
        self._error = None
        self.aviso.clear()
        self._empezar_a_medir()
        self.cambio.emit()

    def _buscar_de_nuevo(self) -> None:
        self._parar()
        self._cargar()
        self.cambio.emit()

    def _explicar(self, codigo: str) -> None:
        explicacion = explicar(codigo)
        self.aviso.setText(f"{explicacion.que_paso} {explicacion.que_hacer}")
