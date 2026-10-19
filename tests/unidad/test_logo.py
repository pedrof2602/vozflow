"""El logo propio de vozflow: un cuadrado redondeado azul con barras de onda."""

import os

from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from vozflow.ui.logo import COLOR_DEL_LOGO, logo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _imagen(lado: int = 128):  # type: ignore[no-untyped-def]
    QApplication.instance() or QApplication([])
    return logo(lado).pixmap(lado, lado).toImage()


def test_el_logo_no_esta_vacio_y_respeta_el_tamano() -> None:
    imagen = _imagen(128)

    assert imagen.width() == 128 and not imagen.isNull()


def test_las_esquinas_son_transparentes_porque_el_cuadrado_es_redondeado() -> None:
    imagen = _imagen(128)

    assert imagen.pixelColor(0, 0).alpha() == 0
    assert imagen.pixelColor(127, 127).alpha() == 0


def test_el_fondo_es_el_cherry() -> None:
    imagen = _imagen(128)

    assert imagen.pixelColor(10, 64).name() == COLOR_DEL_LOGO


def test_el_centro_tiene_una_barra_clara() -> None:
    imagen = _imagen(128)

    centro = imagen.pixelColor(64, 64)

    assert centro.red() > 230 and centro.green() > 230 and centro.blue() > 230


def test_las_barras_no_son_todas_iguales() -> None:
    imagen = _imagen(128)

    alturas = []
    for x in (40, 52, 64, 76, 88):
        alturas.append(sum(1 for y in range(128) if imagen.pixelColor(x, y).red() > 230))

    assert len(set(alturas)) > 1


def test_la_ventana_de_ajustes_lleva_el_logo(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QLabel

    from vozflow.ui.ajustes.ventana import VentanaAjustes

    ventana = VentanaAjustes({"Uno": QLabel("uno")})
    qtbot.addWidget(ventana)

    assert not ventana.windowIcon().isNull()
