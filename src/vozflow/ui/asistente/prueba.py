"""Paso de prueba del asistente (002, RP-010): dictar una frase y ver el texto ahí mismo.

Nunca pega en otra ventana ni guarda nada en el historial: el paso solo conoce un ``Probador``.
Si falta el modelo de voz, ofrece descargarlo con una barra de avance.
"""

import logging
from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

from vozflow.audio.captura import ErrorDeAudio
from vozflow.barra import barra_de_texto
from vozflow.mensajes import explicar
from vozflow.ui.asistente.base import PasoDelAsistente

_registro = logging.getLogger(__name__)


class Probador(Protocol):
    """Lo que el paso necesita para probar la voz; los métodos lentos avisan por callbacks, que
    pueden llegar desde otro hilo."""

    def modelo_descargado(self) -> bool: ...

    def descargar_modelo(
        self,
        al_avance: Callable[[int, int], None],
        al_listo: Callable[[], None],
        al_error: Callable[[str], None],
    ) -> None: ...

    def preparar(self, al_listo: Callable[[], None], al_error: Callable[[str], None]) -> None: ...

    def empezar(self) -> None: ...

    def terminar(
        self, al_resultado: Callable[[str], None], al_error: Callable[[str], None]
    ) -> None: ...

    def cancelar(self) -> None: ...


class PasoPrueba(PasoDelAsistente):
    TITULO = "Probá tu voz"

    # Las señales llevan los resultados de otros hilos al hilo de la ventana.
    _modelo_listo = Signal()
    _modelo_con_error = Signal(str)
    _descarga_lista = Signal()
    _descarga_con_error = Signal(str)
    _avanzo = Signal(int, int)
    _entendido = Signal(str)
    _no_entendido = Signal(str)

    def __init__(self, probador: Probador) -> None:
        super().__init__()
        self._probador = probador
        self._grabando = False
        self.boton_grabar = QPushButton("Grabar")
        self.boton_grabar.setProperty("principal", True)
        self.boton_descargar = QPushButton("Descargar el modelo de voz")
        self.boton_reintentar = QPushButton("Reintentar")
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self._progreso = QLabel()
        self.etiqueta_resultado = QLabel()
        self.etiqueta_resultado.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_resultado.setWordWrap(True)
        self.etiqueta_resultado.setObjectName("comando")
        self.etiqueta_resultado.hide()
        ayuda = QLabel(
            "Apretá «Grabar», decí una frase y apretá «Listo, terminé»: te mostramos acá lo que "
            "entendimos. No se pega en ningún lado."
        )
        ayuda.setWordWrap(True)
        columna = QVBoxLayout(self)
        for widget in (
            ayuda,
            self.aviso,
            self._progreso,
            self.etiqueta_resultado,
            self.boton_grabar,
            self.boton_descargar,
            self.boton_reintentar,
        ):
            columna.addWidget(widget)
        columna.addStretch()
        self.boton_grabar.clicked.connect(lambda _=False: self._grabar_o_terminar())
        self.boton_descargar.clicked.connect(lambda _=False: self._descargar())
        self.boton_reintentar.clicked.connect(lambda _=False: self._preparar())
        self._modelo_listo.connect(self._al_estar_listo)
        self._modelo_con_error.connect(lambda _: self._al_fallar_el_modelo("generico"))
        self._descarga_lista.connect(self._preparar)
        self._descarga_con_error.connect(lambda _: self._al_fallar_la_descarga())
        self._avanzo.connect(self._mostrar_avance)
        self._entendido.connect(self._mostrar_resultado)
        self._no_entendido.connect(lambda _: self._no_se_pudo_entender())

    # ---- el paso ----

    def puede_avanzar(self) -> bool:
        return True  # la prueba ayuda, pero nunca traba a nadie

    def al_entrar(self) -> None:
        self._grabando = False
        self.etiqueta_resultado.hide()
        self.boton_grabar.setText("Grabar")
        self.boton_descargar.hide()
        self.boton_reintentar.hide()
        self._progreso.clear()
        if self._probador.modelo_descargado():
            self._preparar()
        else:
            self._sin_modelo()

    def al_salir(self) -> None:
        if self._grabando:
            self._probador.cancelar()
            self._grabando = False

    def texto(self) -> str:
        return self.etiqueta_resultado.text()

    def texto_de_progreso(self) -> str:
        return self._progreso.text()

    # ---- el modelo ----

    def _sin_modelo(self) -> None:
        self.boton_grabar.setEnabled(False)
        self._avisar("modelo_faltante")
        self.boton_descargar.show()

    def _descargar(self) -> None:
        self.boton_descargar.setEnabled(False)
        self.aviso.setText("Descargando el modelo de voz (una sola vez)…")
        self._probador.descargar_modelo(
            self._avanzo.emit, self._descarga_lista.emit, self._descarga_con_error.emit
        )

    def _mostrar_avance(self, hechos: int, total: int) -> None:
        self._progreso.setText(barra_de_texto(hechos, total))

    def _al_fallar_la_descarga(self) -> None:
        self.boton_descargar.setEnabled(True)
        self.boton_descargar.show()
        self._progreso.clear()
        self._avisar("modelo_faltante")

    def _preparar(self) -> None:
        self.boton_descargar.hide()
        self.boton_reintentar.hide()
        self.boton_grabar.setEnabled(False)
        self.aviso.setText("Preparando el modelo de voz… son unos segundos.")
        self._probador.preparar(self._modelo_listo.emit, self._modelo_con_error.emit)

    def _al_estar_listo(self) -> None:
        self.aviso.clear()
        self.boton_grabar.setEnabled(True)

    def _al_fallar_el_modelo(self, codigo: str) -> None:
        self._avisar(codigo)
        self.boton_grabar.setEnabled(False)
        self.boton_reintentar.show()

    # ---- grabar y entender ----

    def _grabar_o_terminar(self) -> None:
        if self._grabando:
            self._terminar()
        else:
            self._empezar()

    def _empezar(self) -> None:
        self.etiqueta_resultado.hide()
        self.aviso.clear()
        try:
            self._probador.empezar()
        except ErrorDeAudio as error:
            _registro.warning("No se pudo grabar la prueba: %s", error)
            self._avisar(error.codigo)
            self.boton_grabar.setText("Grabar")
            return
        self._grabando = True
        self.boton_grabar.setText("Listo, terminé")

    def _terminar(self) -> None:
        self._grabando = False
        self.boton_grabar.setEnabled(False)
        self.aviso.setText("Entendiendo lo que dijiste…")
        self._probador.terminar(self._entendido.emit, self._no_entendido.emit)

    def _no_se_pudo_entender(self) -> None:
        self._avisar("generico")
        self.boton_grabar.setEnabled(True)
        self.boton_grabar.setText("Probar de nuevo")

    def _mostrar_resultado(self, texto: str) -> None:
        self.boton_grabar.setEnabled(True)
        self.boton_grabar.setText("Probar de nuevo")
        if not texto.strip():
            self.aviso.setText("No te escuché. Probá hablar más cerca del micrófono.")
            return
        self.aviso.clear()
        self.etiqueta_resultado.setText(texto)
        self.etiqueta_resultado.show()
        self.cambio.emit()

    def _avisar(self, codigo: str) -> None:
        explicacion = explicar(codigo)
        self.aviso.setText(f"{explicacion.que_paso} {explicacion.que_hacer}")
