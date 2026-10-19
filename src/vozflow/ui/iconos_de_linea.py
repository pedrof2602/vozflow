"""Íconos de línea propios, de 24 × 24, dibujados en código.

Son rutas SVG simples (trazo redondeado, sin relleno) escritas para vozflow: se tiñen con el color
que se pida, para que sigan al tema claro u oscuro.
"""

import re

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_FORMAS = {
    "historial": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "vocabulario": (
        '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z"/>'
        '<path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3"/>'
    ),
    "modos": (
        '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/>'
        '<circle cx="9" cy="17" r="2"/>'
    ),
    "teclas": (
        '<rect x="2" y="6" width="20" height="12" rx="2"/>'
        '<path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7.5 14h9"/>'
    ),
    "audio": (
        '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'
    ),
    "reescritura": (
        '<path d="M11 3l1.9 4.9L18 10l-5.1 2.1L11 17l-1.9-4.9L4 10l5.1-2.1z"/>'
        '<path d="M19 15v4M17 17h4"/>'
    ),
    "copia": '<path d="M4 8h16v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM3 4h18v4H3zM10 12h4"/>',
    "ajustes": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1'
        'M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>'
    ),
    "buscar": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>',
    "copiar": (
        '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>'
    ),
    "insertar": '<path d="M9 10l-5 5 5 5"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/>',
    "borrar": (
        '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>'
    ),
    "mas": '<path d="M12 5v14M5 12h14"/>',
    "cerrar": '<path d="M6 6l12 12M18 6L6 18"/>',
    "derecha": '<path d="M9 6l6 6-6 6"/>',
    "abajo": '<path d="M6 9l6 6 6-6"/>',
    "pausa": '<path d="M8 5v14M16 5v14"/>',
    "traducir": (
        '<path d="M4 5h9M8.5 3v2M6 5c.5 4 2.5 6.5 6 8M12 5c-.5 3-2.5 6-7 8.5'
        'M12 20l4-9 4 9M13.5 17h5"/>'
    ),
}
NOMBRES = tuple(_FORMAS)

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def svg_de(nombre: str, color: str) -> str:
    """El SVG del ícono ``nombre`` con el trazo de ``color`` (``#rrggbb``)."""
    if not _COLOR.match(color):
        raise ValueError(f"El color {color!r} no es de la forma #rrggbb")
    try:
        formas = _FORMAS[nombre]
    except KeyError:
        raise KeyError(f"No existe el ícono «{nombre}»") from None
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" '
        f'stroke-linejoin="round">{formas}</svg>'
    )


def icono(nombre: str, color: str, tamano: int = 18) -> QIcon:
    """Un ``QIcon`` nítido a ``tamano`` píxeles (y al doble, para pantallas de alta densidad)."""
    renderizador = QSvgRenderer(QByteArray(svg_de(nombre, color).encode("utf-8")))
    resultado = QIcon()
    for escala in (1, 2):
        lado = tamano * escala
        imagen = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
        imagen.fill(Qt.GlobalColor.transparent)
        pintor = QPainter(imagen)
        renderizador.render(pintor)
        pintor.end()
        resultado.addPixmap(QPixmap.fromImage(imagen))
    return resultado
