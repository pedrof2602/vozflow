"""El logo de vozflow, dibujado en código: un cuadrado redondeado cherry con barras de onda."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

COLOR_DEL_LOGO = "#b64f67"
_ALTURAS = (0.22, 0.46, 0.74, 0.46, 0.22)  # fracción del lado, de izquierda a derecha


MARCA_DEL_SVG = "<!-- Generado por vozflow -->"
_PROPORCION_DE_ESQUINA = 0.22
_PROPORCION_DE_BARRA = 0.08
_PROPORCION_DE_HUECO = 0.075


def svg_del_logo() -> str:
    """El logo como SVG de 256 × 256 (ícono del menú); sale de las mismas medidas que se dibujan."""
    lado = 256.0
    ancho, hueco = lado * _PROPORCION_DE_BARRA, lado * _PROPORCION_DE_HUECO
    total = len(_ALTURAS) * ancho + (len(_ALTURAS) - 1) * hueco
    x = (lado - total) / 2
    barras = []
    for fraccion in _ALTURAS:
        alto = lado * fraccion
        barras.append(
            f'  <rect x="{x:.2f}" y="{(lado - alto) / 2:.2f}" width="{ancho:.2f}" '
            f'height="{alto:.2f}" rx="{ancho / 2:.2f}" fill="#ffffff"/>'
        )
        x += ancho + hueco
    esquina = lado * _PROPORCION_DE_ESQUINA
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
            'viewBox="0 0 256 256">',
            f"  {MARCA_DEL_SVG}",
            f'  <rect width="256" height="256" rx="{esquina:.2f}" fill="{COLOR_DEL_LOGO}"/>',
            *barras,
            "</svg>",
            "",
        ]
    )


def _dibujar(lado: int) -> QPixmap:
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor(COLOR_DEL_LOGO))
    pintor.drawRoundedRect(
        QRectF(0, 0, lado, lado), lado * _PROPORCION_DE_ESQUINA, lado * _PROPORCION_DE_ESQUINA
    )
    pintor.setBrush(QColor("#ffffff"))
    ancho, hueco = lado * _PROPORCION_DE_BARRA, lado * _PROPORCION_DE_HUECO
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
