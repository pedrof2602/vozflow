"""Íconos de línea propios: SVG de 24 × 24 que se tiñen con el color del texto."""

import re
import xml.etree.ElementTree as ET

import pytest

from vozflow.ui.iconos_de_linea import NOMBRES, svg_de

USADOS_POR_LA_INTERFAZ = [
    "historial", "vocabulario", "modos", "teclas", "audio", "reescritura", "copia", "ajustes",
    "buscar", "copiar", "insertar", "borrar", "mas", "cerrar", "pausa", "traducir", "derecha", "abajo",
]  # fmt: skip


def test_estan_todos_los_que_usa_la_interfaz() -> None:
    assert set(USADOS_POR_LA_INTERFAZ) <= set(NOMBRES)


@pytest.mark.parametrize("nombre", NOMBRES)
def test_cada_icono_es_un_svg_valido_de_24(nombre: str) -> None:
    raiz = ET.fromstring(svg_de(nombre, "#abcdef"))

    assert raiz.tag.endswith("svg") and raiz.attrib["viewBox"] == "0 0 24 24"


@pytest.mark.parametrize("nombre", NOMBRES)
def test_cada_icono_se_tine_con_el_color_pedido(nombre: str) -> None:
    svg = svg_de(nombre, "#abcdef")

    assert 'stroke="#abcdef"' in svg
    assert "currentColor" not in svg


@pytest.mark.parametrize("nombre", NOMBRES)
def test_los_iconos_son_de_linea_y_sin_relleno(nombre: str) -> None:
    svg = svg_de(nombre, "#abcdef")

    assert 'fill="none"' in svg and 'stroke-linecap="round"' in svg


@pytest.mark.parametrize("color", ["#fff", "rojo", "#12345", "javascript:x", '"><script>'])
def test_un_color_invalido_se_rechaza(color: str) -> None:
    with pytest.raises(ValueError, match="color"):
        svg_de("buscar", color)


def test_un_nombre_desconocido_es_un_error_claro() -> None:
    with pytest.raises(KeyError, match="ícono"):
        svg_de("no-existe", "#abcdef")


def test_los_nombres_son_unicos_y_en_minusculas() -> None:
    assert len(set(NOMBRES)) == len(NOMBRES)
    assert all(re.fullmatch(r"[a-z]+", n) for n in NOMBRES)


@pytest.mark.parametrize("nombre", NOMBRES)
def test_con_qt_cada_icono_dibuja_algo(nombre: str) -> None:
    from PySide6.QtWidgets import QApplication

    from vozflow.ui.iconos_de_linea import icono

    app = QApplication.instance() or QApplication([])
    imagen = icono(nombre, "#e8e8e8", 24).pixmap(24, 24).toImage()

    visibles = sum(1 for x in range(24) for y in range(24) if imagen.pixelColor(x, y).alpha() > 0)
    assert visibles > 10 and app is not None


def test_el_tamano_pedido_se_respeta() -> None:
    from PySide6.QtWidgets import QApplication

    from vozflow.ui.iconos_de_linea import icono

    QApplication.instance() or QApplication([])

    assert icono("buscar", "#ffffff", 32).pixmap(32, 32).width() == 32
