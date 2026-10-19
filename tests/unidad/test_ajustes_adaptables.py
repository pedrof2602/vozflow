"""Los ajustes se adaptan al ancho de la ventana: nada se corta aunque los nombres sean largos."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QWidget
from pytestqt.qtbot import QtBot

from tests.unidad.test_ventana_ajustes import _contexto
from vozflow.audio.captura import Dispositivo
from vozflow.ui.ajustes.ventana import VentanaAjustes, crear_paginas
from vozflow.ui.componentes import acotar_combo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

NOMBRES_LARGOS = [
    Dispositivo(i, f"HDA Intel PCH: ALC256 Analog (hw:0,{i}) con un nombre larguísimo de verdad y todavía más largo: " + "x" * 90, 2,
                es_predeterminado=(i == 0))
    for i in range(12)
]  # fmt: skip
ANCHO_DEL_CONTENIDO = 700  # lo que queda de una ventana de ~950 px al descontar la barra lateral


def test_un_combo_acotado_no_pide_el_ancho_de_su_item_mas_largo(qtbot: QtBot) -> None:
    combo = QComboBox()
    combo.addItem("x" * 200)
    qtbot.addWidget(combo)
    sin_acotar = QComboBox()
    sin_acotar.addItem("x" * 200)
    qtbot.addWidget(sin_acotar)
    sin_acotar.show()
    ancho_sin_acotar = sin_acotar.minimumSizeHint().width()

    acotar_combo(combo)  # como en las páginas: al construirlas, antes de mostrarse
    combo.show()

    assert combo.minimumSizeHint().width() < ancho_sin_acotar / 2
    assert combo.minimumSizeHint().width() < 400


def test_acotar_un_combo_no_cambia_sus_opciones(qtbot: QtBot) -> None:
    combo = QComboBox()
    combo.addItem("Uno", 1)
    combo.addItem("Dos", 2)
    qtbot.addWidget(combo)

    acotar_combo(combo)

    assert [combo.itemData(i) for i in range(2)] == [1, 2] and combo.currentText() == "Uno"


def _ventana(qtbot: QtBot, tmp_path: Path) -> VentanaAjustes:
    contexto = _contexto(tmp_path)
    contexto.listar_dispositivos = lambda: NOMBRES_LARGOS
    ventana = VentanaAjustes(crear_paginas(contexto, lambda accion: accion()))
    qtbot.addWidget(ventana)
    return ventana


@pytest.mark.parametrize(
    "pagina",
    [
        "Dictado", "Vocabulario", "Historial", "General", "Otras teclas", "Modos",
        "Modelo y rendimiento", "Asistente de IA", "Copia de seguridad",
    ],
)  # fmt: skip
def test_ninguna_pagina_pide_mas_ancho_del_que_hay(
    qtbot: QtBot, tmp_path: Path, pagina: str
) -> None:
    ventana = _ventana(qtbot, tmp_path)
    ventana.show()  # Qt calcula el ancho de los combos al mostrarse por primera vez
    ventana.mostrar_pagina(pagina)
    QApplication.processEvents()

    pedido = ventana.widget_de_pagina(pagina).minimumSizeHint().width()

    assert pedido <= ANCHO_DEL_CONTENIDO, f"{pagina} pide {pedido} px"


def test_con_la_ventana_angosta_los_controles_de_dictado_quedan_a_la_vista(
    qtbot: QtBot, tmp_path: Path
) -> None:
    ventana = _ventana(qtbot, tmp_path)
    ventana.resize(950, 640)
    ventana.show()
    ventana.mostrar_pagina("Dictado")
    pagina: QWidget = ventana.widget_de_pagina("Dictado")

    for control in pagina.findChildren(QComboBox):
        derecha = control.mapTo(pagina, control.rect().topRight()).x()
        assert derecha <= pagina.width(), control.currentText()
