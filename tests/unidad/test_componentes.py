"""Componentes propios del aspecto: interruptor, teclas, tarjeta, chips y filas de ajuste."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QLabel, QWidget
from pytestqt.qtbot import QtBot

from vozflow.ui.componentes import (
    Chips,
    EncabezadoDeSeccion,
    FilaDeAjuste,
    FilaDeTeclas,
    Interruptor,
    Tarjeta,
    teclas_de,
)
from vozflow.ui.tema import CLARA, OSCURA, establecer_paleta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _paleta_oscura() -> None:
    establecer_paleta(OSCURA)


def _pixeles(widget: QWidget) -> QImage:
    widget.resize(widget.sizeHint())
    imagen: QImage = widget.grab().toImage()
    return imagen


# ---- interruptor ---------------------------------------------------------------------------------


def test_el_interruptor_es_un_checkbox_con_el_mismo_comportamiento(qtbot: QtBot) -> None:
    interruptor = Interruptor("Mostrar el indicador")
    qtbot.addWidget(interruptor)

    assert isinstance(interruptor, QCheckBox) and interruptor.text() == "Mostrar el indicador"
    assert interruptor.isChecked() is False
    interruptor.setChecked(True)
    assert interruptor.isChecked() is True


def test_el_interruptor_avisa_cuando_cambia(qtbot: QtBot) -> None:
    interruptor = Interruptor()
    qtbot.addWidget(interruptor)

    with qtbot.waitSignal(interruptor.toggled) as senal:
        QTest.mouseClick(interruptor, Qt.MouseButton.LeftButton)

    assert senal.args == [True] and interruptor.isChecked()


def test_el_interruptor_se_maneja_con_el_teclado(qtbot: QtBot) -> None:
    interruptor = Interruptor()
    qtbot.addWidget(interruptor)
    interruptor.show()
    interruptor.setFocus()

    QTest.keyClick(interruptor, Qt.Key.Key_Space)

    assert interruptor.isChecked()


def test_un_interruptor_apagado_y_uno_encendido_se_ven_distintos(qtbot: QtBot) -> None:
    interruptor = Interruptor()
    qtbot.addWidget(interruptor)
    apagado = _pixeles(interruptor)
    interruptor.setChecked(True)
    encendido = _pixeles(interruptor)

    assert apagado != encendido


def test_el_interruptor_encendido_usa_el_color_primario_de_la_paleta(qtbot: QtBot) -> None:
    interruptor = Interruptor()
    qtbot.addWidget(interruptor)
    interruptor.setChecked(True)

    imagen = _pixeles(interruptor)
    colores = {imagen.pixelColor(x, imagen.height() // 2).name() for x in range(imagen.width())}

    assert OSCURA.primario in colores


def test_el_interruptor_sigue_a_la_paleta_en_uso(qtbot: QtBot) -> None:
    interruptor = Interruptor()
    qtbot.addWidget(interruptor)
    interruptor.setChecked(True)
    oscuro = _pixeles(interruptor)

    establecer_paleta(CLARA)

    assert _pixeles(interruptor) != oscuro


def test_el_interruptor_deshabilitado_no_cambia(qtbot: QtBot) -> None:
    interruptor = Interruptor()
    qtbot.addWidget(interruptor)
    interruptor.setEnabled(False)

    QTest.mouseClick(interruptor, Qt.MouseButton.LeftButton)

    assert not interruptor.isChecked()


# ---- teclas dibujadas ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("atajo", "esperado"),
    [
        ("RightCtrl", ["Ctrl der."]),
        ("LeftCtrl", ["Ctrl izq."]),
        ("RightAlt", ["Alt der."]),
        ("LeftShift", ["Shift izq."]),
        ("<Control><Alt>space", ["Ctrl", "Alt", "Espacio"]),
        ("Ctrl+Alt+D", ["Ctrl", "Alt", "D"]),
        ("<Control><Alt>d", ["Ctrl", "Alt", "D"]),
        ("F9", ["F9"]),
        ("Ctrl+Shift+Return", ["Ctrl", "Shift", "Intro"]),
        ("<Super>d", ["Super", "D"]),
        ("Ctrl+Insert", ["Ctrl", "Insert"]),
    ],
)
def test_un_atajo_se_separa_en_teclas_legibles(atajo: str, esperado: list[str]) -> None:
    assert teclas_de(atajo) == esperado


def test_un_atajo_vacio_no_tiene_teclas() -> None:
    assert teclas_de("") == [] and teclas_de("   ") == []


def test_la_fila_de_teclas_dibuja_una_tecla_por_cada_una(qtbot: QtBot) -> None:
    fila = FilaDeTeclas("<Control><Alt>space")
    qtbot.addWidget(fila)

    assert fila.textos() == ["Ctrl", "Alt", "Espacio"]


def test_la_fila_de_teclas_se_actualiza(qtbot: QtBot) -> None:
    fila = FilaDeTeclas("F9")
    qtbot.addWidget(fila)

    fila.establecer("Ctrl+D")

    assert fila.textos() == ["Ctrl", "D"]


# ---- tarjeta, encabezado y filas -----------------------------------------------------------------------


def test_la_tarjeta_muestra_titulo_y_descripcion(qtbot: QtBot) -> None:
    tarjeta = Tarjeta("Teclas", "Cómo se empieza a dictar")
    qtbot.addWidget(tarjeta)

    textos = [e.text() for e in tarjeta.findChildren(QLabel)]

    assert "Teclas" in textos and "Cómo se empieza a dictar" in textos
    assert tarjeta.objectName() == "tarjeta"


def test_la_tarjeta_aloja_widgets_en_su_cuerpo(qtbot: QtBot) -> None:
    tarjeta = Tarjeta("T")
    qtbot.addWidget(tarjeta)
    etiqueta = QLabel("dentro")

    tarjeta.agregar(etiqueta)

    assert etiqueta.parent() is tarjeta


def test_una_tarjeta_sin_titulo_no_deja_un_hueco(qtbot: QtBot) -> None:
    tarjeta = Tarjeta()
    qtbot.addWidget(tarjeta)

    assert [e for e in tarjeta.findChildren(QLabel) if e.text()] == []


def test_el_encabezado_de_seccion_tiene_titulo_y_descripcion(qtbot: QtBot) -> None:
    encabezado = EncabezadoDeSeccion("Ajustes", "Todo lo configurable")
    qtbot.addWidget(encabezado)

    por_nombre = {e.objectName(): e.text() for e in encabezado.findChildren(QLabel)}

    assert por_nombre["titulo"] == "Ajustes" and por_nombre["descripcion"] == "Todo lo configurable"


def test_la_fila_de_ajuste_pone_el_texto_a_la_izquierda_y_el_control_a_la_derecha(
    qtbot: QtBot,
) -> None:
    control = Interruptor()
    fila = FilaDeAjuste("Indicador", "Mostrar al grabar", control)
    qtbot.addWidget(fila)
    fila.resize(500, 50)
    fila.show()

    titulo = next(e for e in fila.findChildren(QLabel) if e.text() == "Indicador")

    assert control.parent() is fila
    assert titulo.geometry().x() < control.geometry().x()


# ---- chips -------------------------------------------------------------------------------------------------


def _chips(qtbot: QtBot) -> Chips:
    chips = Chips()
    for texto, dato in (
        ("Ollama", "ollama"),
        ("Anthropic", "anthropic"),
        ("OpenRouter", "openrouter"),
    ):
        chips.addItem(texto, dato)
    qtbot.addWidget(chips)
    return chips


def test_los_chips_tienen_la_misma_interfaz_que_un_combo(qtbot: QtBot) -> None:
    chips = _chips(qtbot)

    assert chips.count() == 3
    assert [chips.itemData(i) for i in range(3)] == ["ollama", "anthropic", "openrouter"]
    assert chips.itemText(1) == "Anthropic" and chips.findData("openrouter") == 2
    assert chips.findData("otro") == -1


def test_el_primer_chip_arranca_elegido(qtbot: QtBot) -> None:
    chips = _chips(qtbot)

    assert chips.currentIndex() == 0 and chips.currentData() == "ollama"
    assert chips.currentText() == "Ollama"


def test_elegir_por_indice_cambia_el_dato_y_avisa(qtbot: QtBot) -> None:
    chips = _chips(qtbot)

    with qtbot.waitSignal(chips.currentIndexChanged) as senal:
        chips.setCurrentIndex(2)

    assert senal.args == [2] and chips.currentData() == "openrouter"


def test_solo_un_chip_esta_elegido_a_la_vez(qtbot: QtBot) -> None:
    chips = _chips(qtbot)

    chips.setCurrentIndex(1)

    marcados = [b.isChecked() for b in chips.botones()]
    assert marcados == [False, True, False]


def test_hacer_clic_en_un_chip_lo_elige(qtbot: QtBot) -> None:
    chips = _chips(qtbot)
    chips.show()

    QTest.mouseClick(chips.botones()[1], Qt.MouseButton.LeftButton)

    assert chips.currentData() == "anthropic"


def test_un_indice_fuera_de_rango_no_cambia_nada(qtbot: QtBot) -> None:
    chips = _chips(qtbot)

    chips.setCurrentIndex(7)

    assert chips.currentIndex() == 0


def test_los_chips_vacios_no_fallan(qtbot: QtBot) -> None:
    chips = Chips()
    qtbot.addWidget(chips)

    assert chips.count() == 0 and chips.currentIndex() == -1 and chips.currentData() is None
    assert chips.currentText() == ""
