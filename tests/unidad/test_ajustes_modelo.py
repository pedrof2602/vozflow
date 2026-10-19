"""Página «Modelo y rendimiento» (Avanzado, 002, RP-016): modelo de voz y potencia de cálculo.

Reemplaza a la página de audio: el micrófono, el idioma y el cartel pasaron a «Dictado»
(``test_ajustes_dictado.py``); aquí queda lo técnico que verificaba la antigua.
"""

import os

from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.modelo import PaginaModelo
from vozflow.ui.textos import ayuda_de, texto_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _pagina(qtbot: QtBot):  # type: ignore[no-untyped-def]
    ajustes = AjustesRepo(abrir_base(":memory:"))
    pagina = PaginaModelo(ajustes)
    qtbot.addWidget(pagina)
    pagina.show()
    return pagina, ajustes


def test_arranca_con_los_valores_por_defecto(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    assert pagina.campo_modelo.text() == "small" and pagina.spin_hilos.value() == 4


def test_no_trae_lo_que_paso_a_la_pagina_dictado(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    for nombre in ("combo_microfono", "combo_idioma", "check_indicador", "interruptor_indicador"):
        assert not hasattr(pagina, nombre)


def test_guarda_el_modelo_y_la_potencia(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina(qtbot)
    pagina.campo_modelo.setText("medium")
    pagina.spin_hilos.setValue(6)

    pagina.guardar()

    assert ajustes.obtener("motor.modelo") == "medium" and ajustes.obtener("motor.hilos") == 6
    assert pagina.hay_error is False


def test_muestra_lo_ya_guardado(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("motor.modelo", "base")
    ajustes.establecer("motor.hilos", 2)
    pagina = PaginaModelo(ajustes)
    qtbot.addWidget(pagina)

    assert pagina.campo_modelo.text() == "base" and pagina.spin_hilos.value() == 2


def test_la_potencia_va_de_1_a_8(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    assert (pagina.spin_hilos.minimum(), pagina.spin_hilos.maximum()) == (1, 8)


def test_un_modelo_vacio_se_rechaza_y_no_cambia_nada(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina(qtbot)
    pagina.campo_modelo.setText("  ")
    pagina.spin_hilos.setValue(7)

    pagina.guardar()

    assert pagina.hay_error is True and "modelo" in pagina.mensaje.lower()
    assert ajustes.obtener("motor.hilos") == 4


def test_avisa_que_rige_al_reiniciar(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    pagina.guardar()

    assert "reinici" in pagina.mensaje.lower()


def test_cada_opcion_lleva_su_ayuda_en_lenguaje_llano(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)
    textos = [e.text() for e in pagina.findChildren(QLabel)]

    for clave in ("motor.modelo", "motor.hilos"):
        assert texto_de(clave).titulo in textos and ayuda_de(clave) in textos


def test_restablecer_cada_opcion(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina(qtbot)
    pagina.campo_modelo.setText("medium")
    pagina.spin_hilos.setValue(7)
    pagina.guardar()
    fila_modelo, fila_potencia = pagina.filas["motor.modelo"], pagina.filas["motor.hilos"]
    assert (
        fila_modelo.boton_restablecer is not None and not fila_modelo.boton_restablecer.isHidden()
    )

    fila_modelo.boton_restablecer.click()
    assert fila_potencia.boton_restablecer is not None
    fila_potencia.boton_restablecer.click()

    assert ajustes.obtener("motor.modelo") == "small" and ajustes.obtener("motor.hilos") == 4
    assert pagina.campo_modelo.text() == "small" and pagina.spin_hilos.value() == 4


def test_con_los_valores_de_fabrica_no_hay_restablecer(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    assert all(
        f.boton_restablecer is not None and f.boton_restablecer.isHidden()
        for f in pagina.filas.values()
    )


def test_estan_las_claves_para_el_inventario() -> None:
    assert PaginaModelo.CLAVES == ("motor.modelo", "motor.hilos")
