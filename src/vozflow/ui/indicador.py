"""Indicador flotante de grabación (RF-028).

Es una ventana sin bordes, siempre arriba, que **no acepta el foco ni los clics**: si robara el
foco, el texto dictado se insertaría en el indicador y no en la aplicación de la persona. El plan B,
si en el escritorio real igual lo roba, es reemplazarlo por una notificación (research.md).
"""

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from vozflow.dominio.dictado import EstadoDelDictado
from vozflow.ui.estado import vista_de

_ANCHO, _ALTO, _SEPARACION_DEL_BORDE = 220, 44, 48


class Indicador(QWidget):
    def __init__(
        self, activo: Callable[[], bool] = lambda: True, duracion_error_ms: int = 3000
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput,
        )
        self._activo = activo
        self._duracion_error_ms = duracion_error_ms
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(_ANCHO, _ALTO)
        self.texto = ""
        self.nivel = 0.0
        self._color = QColor("#8a8f98")
        self._ocultar_error = QTimer(self)
        self._ocultar_error.setSingleShot(True)
        self._ocultar_error.timeout.connect(self.hide)

    def establecer_estado(self, estado: EstadoDelDictado) -> None:
        vista = vista_de(estado)
        self.texto, self._color = vista.texto, QColor(vista.color)
        self._ocultar_error.stop()
        if estado is EstadoDelDictado.INACTIVO or not self._activo():
            self.hide()
            return
        if estado is EstadoDelDictado.ESCUCHANDO:
            self.nivel = 0.0
        if estado is EstadoDelDictado.ERROR:
            self._ocultar_error.start(self._duracion_error_ms)
        self._ubicar()
        self.show()
        self.update()

    def establecer_nivel(self, nivel: float) -> None:
        self.nivel = min(1.0, max(0.0, nivel))
        if self.isVisible():
            self.update()

    # ---- internos -----------------------------------------------------------------------

    def _ubicar(self) -> None:
        pantalla = (self.screen() or self.windowHandle().screen()).availableGeometry()
        x = pantalla.center().x() - _ANCHO // 2
        y = pantalla.bottom() - _ALTO - _SEPARACION_DEL_BORDE
        self.move(x, y)

    def paintEvent(self, evento: QPaintEvent) -> None:  # noqa: N802 (nombre de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        fondo = QRectF(0, 0, self.width(), self.height())
        pintor.setBrush(QColor(24, 26, 31, 225))
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.drawRoundedRect(fondo, 14, 14)
        pintor.setBrush(self._color)
        pintor.drawEllipse(QRectF(14, self.height() / 2 - 6, 12, 12))
        fuente = QFont()
        fuente.setPixelSize(14)
        pintor.setFont(fuente)
        pintor.setPen(QColor("white"))
        pintor.drawText(
            QRectF(34, 4, 140, self.height() - 22), Qt.AlignmentFlag.AlignVCenter, self.texto
        )
        # barra de nivel
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(255, 255, 255, 40))
        pista = QRectF(34, self.height() - 14, self.width() - 48, 5)
        pintor.drawRoundedRect(pista, 2.5, 2.5)
        pintor.setBrush(self._color)
        pintor.drawRoundedRect(
            QRectF(pista.x(), pista.y(), pista.width() * self.nivel, 5), 2.5, 2.5
        )
        pintor.end()
