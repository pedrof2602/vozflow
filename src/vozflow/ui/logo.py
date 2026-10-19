"""El logo de vozflow, dibujado en código: un cuadrado redondeado azul con barras de onda."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

AZUL_DEL_LOGO = "#2f6fe0"
_ALTURAS = (0.22, 0.46, 0.74, 0.46, 0.22)  # fracción del lado, de izquierda a derecha


def _dibujar(lado: int) -> QPixmap:
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor(AZUL_DEL_LOGO))
    pintor.drawRoundedRect(QRectF(0, 0, lado, lado), lado * 0.22, lado * 0.22)
    pintor.setBrush(QColor("#ffffff"))
    ancho, hueco = lado * 0.08, lado * 0.075
    total = len(_ALTURAS) * ancho + (len(_ALTURAS) - 1) * hueco
    x = (lado - total) / 2
    for fraccion in _ALTURAS:
        alto = lado * fraccion
        pintor.drawRoundedRect(QRectF(x, (lado - alto) / 2, ancho, alto), ancho / 2, ancho / 2)
        x += ancho + hueco
    pintor.end()
    return QPixmap.fromImage(imagen)


def logo(lado: int = 64) -> QIcon:
    """El logo a ``lado`` píxeles, y a otros tamaños comunes para que no se vea borroso."""
    icono = QIcon()
    for tamano in {lado, 16, 32, 48, 64, 128, 256}:
        icono.addPixmap(_dibujar(tamano))
    return icono
