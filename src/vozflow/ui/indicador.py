"""Indicador flotante de grabación (RF-028).

Es una ventana sin bordes, siempre arriba, que **no acepta el foco ni los clics**: si robara el
foco, el texto dictado se insertaría en el indicador y no en la aplicación de la persona. El plan B,
si en el escritorio real igual lo roba, es reemplazarlo por una notificación (research.md).
"""

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from vozflow.dominio.dictado import EstadoDelDictado
from vozflow.ui.estado import vista_de

_ANCHO, _ALTO, _SEPARACION_DEL_BORDE = 264, 44, 48
_CANTIDAD_DE_BARRAS = 9
_REPOSO = 0.12  # la altura de una barra sin voz, como fracción del espacio disponible
_FONDO = "#191b1d"  # la píldora es oscura en ambos temas, como la de OpenWhispr
_TEXTO = "#e8e8e8"


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
        self._historial = [0.0] * _CANTIDAD_DE_BARRAS
        self._color = QColor("#8a8f98")
        self._ocultar_error = QTimer(self)
        self._ocultar_error.setSingleShot(True)
        self._ocultar_error.timeout.connect(self.hide)

    def establecer_estado(
        self,
        estado: EstadoDelDictado,
        traduciendo_a: str | None = None,
        mejorando: bool = False,
    ) -> None:
        vista = vista_de(estado)
        self.texto, self._color = vista.texto, QColor(vista.color)
        if traduciendo_a and estado is not EstadoDelDictado.INACTIVO:
            self.texto = f"{vista.texto} → {traduciendo_a}"
        elif mejorando and estado is not EstadoDelDictado.INACTIVO:
            self.texto = f"{vista.texto} · IA"
        self._ocultar_error.stop()
        if estado is EstadoDelDictado.INACTIVO or not self._activo():
            self.hide()
            return
        if estado is EstadoDelDictado.ESCUCHANDO:
            self.nivel = 0.0
            self._historial = [0.0] * _CANTIDAD_DE_BARRAS
        if estado is EstadoDelDictado.ERROR:
            self._ocultar_error.start(self._duracion_error_ms)
        self._ubicar()
        self.show()
        self.update()

    def establecer_nivel(self, nivel: float) -> None:
        self.nivel = min(1.0, max(0.0, nivel))
        self._historial = [*self._historial[1:], self.nivel]
        if self.isVisible():
            self.update()

    def barras(self) -> list[float]:
        """Alto de cada barra de onda (0 a 1): las más nuevas a la derecha."""
        return [_REPOSO + (1 - _REPOSO) * nivel for nivel in self._historial]

    def radio_de_esquina(self) -> float:
        return self.height() / 2

    def color_de_fondo(self) -> str:
        return _FONDO

    def color_de_texto(self) -> str:
        return _TEXTO

    def color_del_estado(self) -> str:
        return self._color.name()

    # ---- internos -----------------------------------------------------------------------

    def _ubicar(self) -> None:
        pantalla = (self.screen() or self.windowHandle().screen()).availableGeometry()
        x = pantalla.center().x() - _ANCHO // 2
        y = pantalla.bottom() - _ALTO - _SEPARACION_DEL_BORDE
        self.move(x, y)

    def paintEvent(self, evento: QPaintEvent) -> None:  # noqa: N802 (nombre de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setBrush(QColor(_FONDO))
        pintor.setPen(QPen(QColor("#383b3e"), 1))
        pintor.drawRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
            self.radio_de_esquina(),
            self.radio_de_esquina(),
        )
        # barras de onda
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(self._color)
        ancho_barra, hueco, x = 3.0, 3.0, 20.0
        maximo = self.height() - 18
        for alto in self.barras():
            h = max(4.0, alto * maximo)
            pintor.drawRoundedRect(QRectF(x, (self.height() - h) / 2, ancho_barra, h), 1.5, 1.5)
            x += ancho_barra + hueco
        fuente = QFont()
        fuente.setPixelSize(13)
        pintor.setFont(fuente)
        pintor.setPen(QColor(_TEXTO))
        izquierda = x + 10
        pintor.drawText(
            QRectF(izquierda, 0, self.width() - izquierda - 16, self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self.texto,
        )
        pintor.end()
