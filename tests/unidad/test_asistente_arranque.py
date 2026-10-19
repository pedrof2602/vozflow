"""Paso de arrancar con la sesión: se ofrece, sin imponerlo (002, RP-012, RP-014)."""

import os

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QLineEdit
from pytestqt.qtbot import QtBot

from vozflow.ui.asistente.arranque import PasoArranque
from vozflow.ui.textos import ayuda_de, texto_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class Autoinicio:
    def __init__(self, activo: bool = False, falla: Exception | None = None) -> None:
        self.activo = activo
        self.falla = falla
        self.llamadas: list[bool] = []

    def leer(self) -> bool:
        return self.activo

    def fijar(self, valor: bool) -> None:
        self.llamadas.append(valor)
        if self.falla is not None:
            raise self.falla
        self.activo = valor


def _paso(qtbot: QtBot, autoinicio: Autoinicio | None = None) -> tuple[PasoArranque, Autoinicio]:
    arranque = autoinicio or Autoinicio()
    paso = PasoArranque(arranque.leer, arranque.fijar)
    qtbot.addWidget(paso)
    paso.al_entrar()
    paso.show()
    return paso, arranque


def test_se_ofrece_apagado_sin_imponerlo(qtbot: QtBot) -> None:
    paso, arranque = _paso(qtbot)

    assert paso.interruptor.isChecked() is False and arranque.llamadas == []


def test_si_ya_estaba_activo_lo_muestra_prendido(qtbot: QtBot) -> None:
    paso, _ = _paso(qtbot, Autoinicio(True))

    assert paso.interruptor.isChecked() is True


def test_prenderlo_activa_el_arranque_y_lo_confirma(qtbot: QtBot) -> None:
    paso, arranque = _paso(qtbot)

    QTest.mouseClick(paso.interruptor, Qt.MouseButton.LeftButton)

    assert arranque.activo is True and "arrancará" in paso.aviso.text()


def test_apagarlo_lo_desactiva(qtbot: QtBot) -> None:
    paso, arranque = _paso(qtbot, Autoinicio(True))

    QTest.mouseClick(paso.interruptor, Qt.MouseButton.LeftButton)

    assert arranque.activo is False and "ya no arranca" in paso.aviso.text()


def test_si_no_se_puede_vuelve_atras_y_explica(qtbot: QtBot) -> None:
    paso, arranque = _paso(qtbot, Autoinicio(False, falla=OSError("sin permiso")))

    QTest.mouseClick(paso.interruptor, Qt.MouseButton.LeftButton)

    assert paso.interruptor.isChecked() is False
    assert "sin permiso" in paso.aviso.text() and arranque.llamadas == [True]


def test_siempre_deja_avanzar(qtbot: QtBot) -> None:
    paso, _ = _paso(qtbot)

    assert paso.puede_avanzar() is True


def test_explica_que_es_arrancar_con_la_sesion_con_los_textos_llanos(qtbot: QtBot) -> None:
    paso, _ = _paso(qtbot)
    textos = [e.text() for e in paso.findChildren(QLabel)]

    assert texto_de("autoinicio").titulo in textos and ayuda_de("autoinicio") in textos
    assert PasoArranque.TITULO == "Arrancar con tu computadora"


def test_no_pide_cuentas_claves_ni_datos_personales(qtbot: QtBot) -> None:
    paso, _ = _paso(qtbot)

    assert paso.findChildren(QLineEdit) == []
    texto = " ".join(e.text() for e in paso.findChildren(QLabel)).lower()
    assert not [p for p in ("contraseña", "correo", "email", "cuenta de", "clave") if p in texto]
