"""Íconos dibujados en código, uno por estado: la forma cambia, no solo el color."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from vozflow.ui.estado import VistaDeEstado

_LADO = 64


def icono_de(vista: VistaDeEstado) -> QIcon:
    pixmap = QPixmap(_LADO, _LADO)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(vista.color)
    margen = _LADO * 0.14
    area = QRectF(margen, margen, _LADO - 2 * margen, _LADO - 2 * margen)
    if vista.icono == "inactivo":  # un anillo vacío
        pintor.setPen(QPen(color, _LADO * 0.1))
        pintor.drawEllipse(area)
    elif vista.icono == "escuchando":  # un círculo lleno
        pintor.setBrush(color)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.drawEllipse(area)
    elif vista.icono == "transcribiendo":  # tres puntos
        pintor.setBrush(color)
        pintor.setPen(Qt.PenStyle.NoPen)
        radio = _LADO * 0.1
        for i in range(3):
            pintor.drawEllipse(QPointF(_LADO * (0.22 + 0.28 * i), _LADO / 2), radio, radio)
    else:  # error: un círculo con una exclamación
        pintor.setBrush(color)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.drawEllipse(area)
        pintor.setPen(QColor("white"))
        fuente = QFont()
        fuente.setBold(True)
        fuente.setPixelSize(int(_LADO * 0.55))
        pintor.setFont(fuente)
        pintor.drawText(area, Qt.AlignmentFlag.AlignCenter, "!")
    pintor.end()
    return QIcon(pixmap)
