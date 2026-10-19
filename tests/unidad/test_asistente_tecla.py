"""Paso de la tecla del asistente: mostrarla, cambiarla y no dejar una que el teclado no tiene (002)."""

import os
from collections.abc import Mapping

from evdev import ecodes
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from vozflow.atajos.puerto import AccionDeAtajo, AtajoOcupado
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.asistente.tecla import PasoTecla

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

COMPLETO = {
    ecodes.KEY_A, ecodes.KEY_SPACE, ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT, ecodes.KEY_F9, ecodes.KEY_F10,
}  # fmt: skip
COMPACTO = COMPLETO - {ecodes.KEY_RIGHTCTRL}


class Aplicador:
    def __init__(self) -> None:
        self.recibidos: list[dict[AccionDeAtajo, str]] = []
        self.error: Exception | None = None

    def __call__(self, atajos: Mapping[AccionDeAtajo, str]) -> None:
        if self.error is not None:
            raise self.error
        self.recibidos.append(dict(atajos))


def _paso(qtbot: QtBot, teclas: set[int] | None = None) -> tuple[PasoTecla, AjustesRepo, Aplicador]:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    aplicador = Aplicador()
    conocidas = COMPLETO if teclas is None else teclas
    paso = PasoTecla(ajustes, aplicador, lambda: conocidas)
    qtbot.addWidget(paso)
    paso.al_entrar()
    paso.show()
    return paso, ajustes, aplicador


def _textos(paso: PasoTecla) -> str:
    return " ".join(e.text() for e in paso.findChildren(QLabel))


def test_muestra_la_tecla_vigente_con_teclas_dibujadas(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot)

    assert paso.teclas.textos() == ["Ctrl der."]
    assert "mantenela apretada" in _textos(paso).lower()


def test_con_una_tecla_que_el_teclado_tiene_se_puede_avanzar(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot)

    assert paso.puede_avanzar() is True and paso.boton_propuesta.isHidden() is True


def test_cambiar_y_apretar_una_tecla_la_aplica_y_la_guarda(qtbot: QtBot) -> None:
    paso, ajustes, aplicador = _paso(qtbot)
    paso.boton_cambiar.click()
    assert paso.campo_tecla.isHidden() is False

    QTest.keyClick(paso.campo_tecla, Qt.Key.Key_F9)

    assert ajustes.obtener("atajo.mantener") == "F9"
    assert aplicador.recibidos[-1][AccionDeAtajo.MANTENER] == "F9"
    assert paso.teclas.textos() == ["F9"] and paso.campo_tecla.isHidden() is True


def test_si_el_teclado_no_tiene_la_tecla_vigente_avisa_y_propone_otra(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot, COMPACTO)

    assert paso.puede_avanzar() is False
    assert "tu teclado no tiene" in _textos(paso).lower()
    assert paso.boton_propuesta.isHidden() is False
    # «Alt der.» ya es la tecla de traducir por defecto: no se propone dos veces.
    assert paso.boton_propuesta.text() == "Usar F9"


def test_usar_la_propuesta_la_aplica_y_deja_avanzar(qtbot: QtBot) -> None:
    paso, ajustes, aplicador = _paso(qtbot, COMPACTO)
    avisos: list[int] = []
    paso.cambio.connect(lambda: avisos.append(1))

    paso.boton_propuesta.click()

    assert ajustes.obtener("atajo.mantener") == "F9"
    assert aplicador.recibidos[-1][AccionDeAtajo.MANTENER] == "F9"
    assert paso.puede_avanzar() is True and paso.boton_propuesta.isHidden() is True
    assert avisos == [1]


def test_una_tecla_elegida_que_el_teclado_no_tiene_se_rechaza(qtbot: QtBot) -> None:
    paso, ajustes, _ = _paso(qtbot, COMPLETO - {ecodes.KEY_F9})
    paso.boton_cambiar.click()

    QTest.keyClick(paso.campo_tecla, Qt.Key.Key_F9)

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert "tu teclado no tiene" in _textos(paso).lower()


def test_si_la_tecla_choca_con_otra_funcion_avisa_y_vuelve_a_la_anterior(qtbot: QtBot) -> None:
    paso, ajustes, aplicador = _paso(qtbot)
    aplicador.error = AtajoOcupado("la usa GNOME")
    paso.boton_cambiar.click()

    QTest.keyClick(paso.campo_tecla, Qt.Key.Key_F9)

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert paso.teclas.textos() == ["Ctrl der."]
    assert paso.hay_error is True


def test_sin_poder_leer_el_teclado_no_se_bloquea_a_nadie(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot, set())

    assert paso.puede_avanzar() is True and paso.boton_propuesta.isHidden() is True


def test_la_propuesta_no_repite_la_tecla_de_otra_funcion(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("atajo.traducir", "F9")  # una de las propuestas ya está en uso
    paso = PasoTecla(ajustes, Aplicador(), lambda: COMPACTO)
    qtbot.addWidget(paso)

    paso.al_entrar()

    assert paso.boton_propuesta.text() == "Usar Alt der."


def test_el_titulo_del_paso() -> None:
    assert PasoTecla.TITULO == "Tu tecla para dictar"
