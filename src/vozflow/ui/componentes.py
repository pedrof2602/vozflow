"""Componentes propios del aspecto de vozflow (guía: ``docs/diseno/referencia-openwhispr.md``).

Los que se dibujan solos (interruptor, teclas) consultan ``paleta_actual()`` al pintarse, así
siguen al tema aunque cambie con la ventana abierta.
"""

import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vozflow.ui.tema import paleta_actual

_ANCHO_PISTA, _ALTO_PISTA = 34, 20
_SEPARACION = 8


class Interruptor(QCheckBox):
    """Un ``QCheckBox`` dibujado como interruptor: mismo comportamiento, otro aspecto."""

    def __init__(self, texto: str = "", padre: QWidget | None = None) -> None:
        super().__init__(texto, padre)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:  # noqa: N802 (nombre de Qt)
        texto = QFontMetrics(self.font()).horizontalAdvance(self.text()) if self.text() else 0
        ancho = _ANCHO_PISTA + (_SEPARACION + texto if texto else 0)
        return QSize(ancho + 4, max(_ALTO_PISTA, QFontMetrics(self.font()).height()) + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def hitButton(self, pos: Any) -> bool:  # noqa: N802
        return bool(self.rect().contains(pos))  # todo el widget es clicable, no solo el cuadrito

    def paintEvent(self, evento: QPaintEvent) -> None:  # noqa: N802
        paleta = paleta_actual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        habilitado = self.isEnabled()
        y = (self.height() - _ALTO_PISTA) / 2
        pista = QRectF(2, y, _ANCHO_PISTA, _ALTO_PISTA)
        if self.isChecked():
            relleno = QColor(paleta.primario if habilitado else paleta.borde_hover)
            borde = relleno
        else:
            relleno = QColor(paleta.superficie_3 if habilitado else paleta.superficie)
            borde = QColor(paleta.borde_hover if habilitado else paleta.borde_suave)
        pintor.setBrush(relleno)
        pintor.setPen(QPen(borde, 1))
        pintor.drawRoundedRect(pista, _ALTO_PISTA / 2, _ALTO_PISTA / 2)
        radio = _ALTO_PISTA / 2 - 3
        centro_x = (
            pista.right() - _ALTO_PISTA / 2 if self.isChecked() else pista.left() + _ALTO_PISTA / 2
        )
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(
            QColor(paleta.texto_sobre_primario if self.isChecked() else paleta.texto_atenuado)
        )
        pintor.drawEllipse(
            QRectF(centro_x - radio, y + _ALTO_PISTA / 2 - radio, 2 * radio, 2 * radio)
        )
        if self.hasFocus():
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.setPen(QPen(QColor(paleta.foco), 2))
            pintor.drawRoundedRect(
                pista.adjusted(-2, -2, 2, 2), _ALTO_PISTA / 2 + 2, _ALTO_PISTA / 2 + 2
            )
        if self.text():
            pintor.setPen(QColor(paleta.texto if habilitado else paleta.texto_atenuado))
            zona = QRectF(2 + _ANCHO_PISTA + _SEPARACION, 0, self.width(), self.height())
            pintor.drawText(
                zona, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text()
            )
        pintor.end()


# ---- teclas dibujadas -------------------------------------------------------------------------

_NOMBRES_LEGIBLES = {
    "control": "Ctrl", "ctrl": "Ctrl", "primary": "Ctrl", "alt": "Alt", "shift": "Shift",
    "super": "Super", "meta": "Super", "space": "Espacio", "espacio": "Espacio",
    "return": "Intro", "enter": "Intro", "esc": "Esc", "escape": "Esc", "del": "Supr",
    "delete": "Supr", "backspace": "Retroceso", "ins": "Insert", "insert": "Insert",
    "scroll_lock": "Bloq Despl", "scrolllock": "Bloq Despl", "grave": "`",
    "altgr": "Alt der.",
}  # fmt: skip
_CON_LADO = re.compile(r"^(left|right|l|r)(ctrl|control|alt|shift|super|meta)$")


def teclas_de(atajo: str) -> list[str]:
    """``<Control><Alt>space`` → ``["Ctrl", "Alt", "Espacio"]``: los nombres para mostrar."""
    legibles: list[str] = []
    for token in (t for t in re.split(r"[+<>\s]+", atajo.strip()) if t):
        bajo = token.lower()
        lado = _CON_LADO.match(bajo)
        if lado:
            nombre = _NOMBRES_LEGIBLES[lado.group(2)]
            legibles.append(f"{nombre} {'izq.' if lado.group(1) in ('left', 'l') else 'der.'}")
        elif bajo in _NOMBRES_LEGIBLES:
            legibles.append(_NOMBRES_LEGIBLES[bajo])
        elif len(token) == 1:
            legibles.append(token.upper())
        else:
            legibles.append(token[0].upper() + token[1:])
    return legibles


class Tecla(QLabel):
    """Una tecla dibujada como tecla: borde, esquinas redondeadas y base más gruesa."""

    def __init__(self, texto: str, padre: QWidget | None = None) -> None:
        super().__init__(texto, padre)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def sizeHint(self) -> QSize:  # noqa: N802
        ancho = QFontMetrics(self.font()).horizontalAdvance(self.text())
        return QSize(max(28, ancho + 20), 26)

    def paintEvent(self, evento: QPaintEvent) -> None:  # noqa: N802
        paleta = paleta_actual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        zona = QRectF(0.5, 0.5, self.width() - 1, self.height() - 2.5)
        pintor.setBrush(QColor(paleta.superficie_3))
        pintor.setPen(QPen(QColor(paleta.borde_hover), 1))
        pintor.drawRoundedRect(zona, 6, 6)
        base = QRectF(3, self.height() - 3, self.width() - 6, 2)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(paleta.borde_hover))
        pintor.drawRoundedRect(base, 1, 1)
        pintor.setPen(QColor(paleta.texto))
        pintor.drawText(zona, int(Qt.AlignmentFlag.AlignCenter), self.text())
        pintor.end()


class FilaDeTeclas(QWidget):
    """Un atajo mostrado como teclas separadas por «+»."""

    def __init__(self, atajo: str = "", padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self._fila = QHBoxLayout(self)
        self._fila.setContentsMargins(0, 0, 0, 0)
        self._fila.setSpacing(4)
        self._textos: list[str] = []
        self.establecer(atajo)

    def establecer(self, atajo: str) -> None:
        while (item := self._fila.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._textos = teclas_de(atajo)
        for i, texto in enumerate(self._textos):
            if i:
                mas = QLabel("+")
                mas.setObjectName("descripcion")
                self._fila.addWidget(mas)
            self._fila.addWidget(Tecla(texto))
        self._fila.addStretch()

    def textos(self) -> list[str]:
        return list(self._textos)


# ---- estructura -------------------------------------------------------------------------------


class EncabezadoDeSeccion(QWidget):
    def __init__(self, titulo: str, descripcion: str = "", padre: QWidget | None = None) -> None:
        super().__init__(padre)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(2)
        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("titulo")
        columna.addWidget(etiqueta)
        if descripcion:
            detalle = QLabel(descripcion)
            detalle.setObjectName("descripcion")
            detalle.setWordWrap(True)
            columna.addWidget(detalle)


class Tarjeta(QFrame):
    """Un bloque redondeado con borde fino y, opcionalmente, título y descripción."""

    def __init__(
        self, titulo: str = "", descripcion: str = "", padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.setObjectName("tarjeta")
        self.cuerpo = QVBoxLayout(self)
        self.cuerpo.setContentsMargins(16, 14, 16, 14)
        self.cuerpo.setSpacing(10)
        if titulo:
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("seccion")
            self.cuerpo.addWidget(etiqueta)
        if descripcion:
            detalle = QLabel(descripcion)
            detalle.setObjectName("descripcion")
            detalle.setWordWrap(True)
            self.cuerpo.addWidget(detalle)

    def agregar(self, widget: QWidget) -> None:
        self.cuerpo.addWidget(widget)


class FilaDeAjuste(QWidget):
    """Título y ayuda a la izquierda, el control a la derecha y, si la opción cambió, «Restablecer».

    ``es_el_original`` dice si el valor es el de fábrica; con ``restablecer`` el botón aparece solo
    cuando no lo es (hay que llamar a ``refrescar`` después de cada cambio).
    """

    def __init__(
        self,
        titulo: str,
        descripcion: str,
        control: QWidget,
        padre: QWidget | None = None,
        *,
        restablecer: Callable[[], None] | None = None,
        es_el_original: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(padre)
        self.titulo = titulo
        self.ayuda = descripcion
        self._restablecer = restablecer
        self._es_el_original = es_el_original
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 4, 0, 4)
        fila.setSpacing(16)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        etiqueta = QLabel(titulo)
        textos.addWidget(etiqueta)
        if descripcion:
            detalle = QLabel(descripcion)
            detalle.setObjectName("descripcion")
            detalle.setWordWrap(True)
            textos.addWidget(detalle)
        fila.addLayout(textos, 1)
        control.setParent(self)
        fila.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.control = control
        self.boton_restablecer: QPushButton | None = None
        if restablecer is not None:
            self.boton_restablecer = QPushButton("Restablecer")
            self.boton_restablecer.setProperty("enlace", True)
            self.boton_restablecer.setCursor(Qt.CursorShape.PointingHandCursor)
            self.boton_restablecer.clicked.connect(lambda _=False: self._al_restablecer())
            fila.addWidget(self.boton_restablecer, 0, Qt.AlignmentFlag.AlignVCenter)
        self.refrescar()

    def refrescar(self) -> None:
        """Muestra u oculta «Restablecer» según el valor actual."""
        if self.boton_restablecer is None:
            return
        original = self._es_el_original() if self._es_el_original is not None else True
        self.boton_restablecer.setVisible(not original)

    def _al_restablecer(self) -> None:
        if self._restablecer is not None:
            self._restablecer()
        self.refrescar()


class MedidorDeNivel(QWidget):
    """Una barra que se llena con el volumen de la voz (0 a 1): así se ve que el micro anda."""

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self._valor = 0.0
        self.setMinimumSize(160, 12)
        self.setMaximumHeight(12)

    def valor(self) -> float:
        return self._valor

    def establecer(self, valor: float) -> None:
        nuevo = min(1.0, max(0.0, valor))
        if nuevo != self._valor:
            self._valor = nuevo
            self.update()

    def paintEvent(self, evento: QPaintEvent) -> None:  # noqa: N802 (nombre de Qt)
        paleta = paleta_actual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(paleta.superficie_3))
        radio = self.height() / 2
        pintor.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radio, radio)
        if self._valor > 0:
            pintor.setBrush(QColor(paleta.primario))
            ancho = max(self.height(), self.width() * self._valor)
            pintor.drawRoundedRect(QRectF(0, 0, ancho, self.height()), radio, radio)
        pintor.end()


# ---- chips ------------------------------------------------------------------------------------


class Chips(QWidget):
    """Un selector de una opción entre pocas, con la interfaz de un ``QComboBox``.

    Se dibuja como la fila de chips de OpenWhispr; las páginas lo usan igual que un combo.
    """

    currentIndexChanged = Signal(int)  # noqa: N815 (nombre de Qt, para ser intercambiable)

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self._fila = QHBoxLayout(self)
        self._fila.setContentsMargins(0, 0, 0, 0)
        self._fila.setSpacing(6)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botones: list[QPushButton] = []
        self._datos: list[Any] = []
        self._indice = -1
        self._fila.addStretch()

    def addItem(self, texto: str, dato: Any = None) -> None:  # noqa: N802
        boton = QPushButton(texto)
        boton.setCheckable(True)
        boton.setProperty("chip", True)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        indice = len(self._botones)
        boton.clicked.connect(lambda _=False, i=indice: self.setCurrentIndex(i))
        self._grupo.addButton(boton)
        self._botones.append(boton)
        self._datos.append(dato)
        self._fila.insertWidget(indice, boton)
        if indice == 0:
            self._indice = 0
            boton.setChecked(True)

    def botones(self) -> list[QPushButton]:
        return list(self._botones)

    def count(self) -> int:
        return len(self._botones)

    def itemData(self, indice: int) -> Any:  # noqa: N802
        return self._datos[indice]

    def itemText(self, indice: int) -> str:  # noqa: N802
        return self._botones[indice].text()

    def findData(self, dato: Any) -> int:  # noqa: N802
        return self._datos.index(dato) if dato in self._datos else -1

    def currentIndex(self) -> int:  # noqa: N802
        return self._indice

    def currentData(self) -> Any:  # noqa: N802
        return self._datos[self._indice] if self._indice >= 0 else None

    def currentText(self) -> str:  # noqa: N802
        return self._botones[self._indice].text() if self._indice >= 0 else ""

    def setCurrentIndex(self, indice: int) -> None:  # noqa: N802
        if not 0 <= indice < len(self._botones) or indice == self._indice:
            return
        self._indice = indice
        self._botones[indice].setChecked(True)
        self.currentIndexChanged.emit(indice)
