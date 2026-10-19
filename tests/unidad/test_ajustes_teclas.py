"""Página de teclas de los ajustes (RF-003, RF-029): capturar, avisar si choca y aplicar sin reiniciar."""

import os
from collections.abc import Mapping

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from pytestqt.qtbot import QtBot

from vozflow.atajos.puerto import AccionDeAtajo, AtajoOcupado
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.teclas import CampoDeAtajo, PaginaTeclas, nombre_de_modificador

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
T = AccionDeAtajo.TRADUCIR

# códigos de tecla del servidor gráfico (xcb) = código de evdev + 8
XCB_CTRL_DERECHO, XCB_CTRL_IZQUIERDO, XCB_ALT_IZQUIERDO = 97 + 8, 29 + 8, 56 + 8


def _tecla(
    tipo: QEvent.Type,
    tecla: Qt.Key,
    modificadores: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    codigo: int = 0,
) -> QKeyEvent:
    return QKeyEvent(tipo, tecla, modificadores, codigo, 0, 0, "")


def _apretar_y_soltar(
    campo: CampoDeAtajo,
    tecla: Qt.Key,
    mods: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    codigo: int = 0,
) -> None:
    campo.keyPressEvent(_tecla(QEvent.Type.KeyPress, tecla, mods, codigo))
    campo.keyReleaseEvent(_tecla(QEvent.Type.KeyRelease, tecla, mods, codigo))


# ---- nombres de los modificadores ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "nombre"),
    [
        (XCB_CTRL_DERECHO, "RightCtrl"),
        (XCB_CTRL_IZQUIERDO, "LeftCtrl"),
        (XCB_ALT_IZQUIERDO, "LeftAlt"),
        (50, "LeftShift"),
        (62, "RightShift"),
        (108, "RightAlt"),
    ],
)
def test_el_codigo_del_teclado_da_el_nombre_con_lado(codigo: int, nombre: str) -> None:
    assert nombre_de_modificador(codigo) == nombre


def test_un_codigo_que_no_es_modificador_no_tiene_nombre() -> None:
    assert nombre_de_modificador(38) is None  # la «a»
    assert nombre_de_modificador(0) is None


# ---- capturar --------------------------------------------------------------------------------------------------


def test_captura_una_combinacion_con_modificadores(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=False)
    qtbot.addWidget(campo)

    _apretar_y_soltar(
        campo,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )

    assert campo.atajo == "Ctrl+Alt+Space"


def test_captura_una_tecla_de_funcion(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=True)
    qtbot.addWidget(campo)

    _apretar_y_soltar(campo, Qt.Key.Key_F9)

    assert campo.atajo == "F9"


def test_un_modificador_solo_se_captura_con_su_lado_si_se_permite(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=True)
    qtbot.addWidget(campo)

    _apretar_y_soltar(
        campo, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier, XCB_CTRL_DERECHO
    )

    assert campo.atajo == "RightCtrl"


def test_un_modificador_solo_no_se_acepta_si_no_se_permite(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=False)
    qtbot.addWidget(campo)
    campo.atajo = "Ctrl+Alt+Space"

    _apretar_y_soltar(
        campo, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier, XCB_CTRL_DERECHO
    )

    assert campo.atajo == "Ctrl+Alt+Space"


def test_un_modificador_seguido_de_otra_tecla_no_cuenta_como_modificador_solo(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=True)
    qtbot.addWidget(campo)

    campo.keyPressEvent(
        _tecla(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Control,
            Qt.KeyboardModifier.ControlModifier,
            XCB_CTRL_IZQUIERDO,
        )
    )
    campo.keyPressEvent(
        _tecla(QEvent.Type.KeyPress, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    )
    campo.keyReleaseEvent(
        _tecla(QEvent.Type.KeyRelease, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    )
    campo.keyReleaseEvent(
        _tecla(
            QEvent.Type.KeyRelease,
            Qt.Key.Key_Control,
            Qt.KeyboardModifier.NoModifier,
            XCB_CTRL_IZQUIERDO,
        )
    )

    assert campo.atajo == "Ctrl+D"


def test_escape_no_se_captura_sino_que_cancela(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=True)
    qtbot.addWidget(campo)
    campo.atajo = "F9"

    _apretar_y_soltar(campo, Qt.Key.Key_Escape)

    assert campo.atajo == "F9"


def test_avisa_cuando_cambia(qtbot: QtBot) -> None:
    campo = CampoDeAtajo(permitir_modificador_solo=True)
    qtbot.addWidget(campo)

    with qtbot.waitSignal(campo.atajo_cambiado) as senal:
        _apretar_y_soltar(campo, Qt.Key.Key_F10)

    assert senal.args == ["F10"]


# ---- la página «Otras teclas» (002: la tecla de dictar pasó a «Dictado») ---------------------------------------


class Aplicador:
    """Hace de «escucha en vivo»: recibe los atajos nuevos o se niega."""

    def __init__(self) -> None:
        self.recibidos: list[Mapping[AccionDeAtajo, str]] = []
        self.error: Exception | None = None

    def __call__(self, atajos: Mapping[AccionDeAtajo, str]) -> None:
        if self.error is not None:
            raise self.error
        self.recibidos.append(dict(atajos))


def _pagina(qtbot: QtBot) -> tuple[PaginaTeclas, AjustesRepo, Aplicador]:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    aplicador = Aplicador()
    pagina = PaginaTeclas(ajustes, aplicador)
    qtbot.addWidget(pagina)
    return pagina, ajustes, aplicador


def test_muestra_las_otras_dos_teclas_y_no_la_de_dictar(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.campo_alternar.atajo == "<Control><Alt>space"
    assert pagina.campo_traducir.atajo == "RightAlt"
    assert not hasattr(pagina, "campo_mantener")


def test_aplicar_cambia_los_atajos_en_vivo_y_los_guarda(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.campo_alternar.atajo = "Ctrl+Alt+D"

    pagina.aplicar()

    assert aplicador.recibidos == [{M: "RightCtrl", A: "<Control><Alt>d", T: "RightAlt"}]
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>d"
    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert "ya funcionan" in pagina.mensaje.lower()


def test_si_choca_con_otra_funcion_avisa_y_no_guarda_nada(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    aplicador.error = AtajoOcupado("<Alt>F4 ya lo usa la función «close» de GNOME")
    pagina.campo_alternar.atajo = "Alt+F4"

    pagina.aplicar()

    assert "close" in pagina.mensaje and pagina.hay_error is True
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>space"
    assert pagina.campo_alternar.atajo == "Alt+F4"  # lo deja para que lo corrija


def test_un_atajo_invalido_se_rechaza_sin_tocar_la_escucha(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.campo_alternar.atajo = "Ctrl"

    pagina.aplicar()

    assert pagina.hay_error is True and aplicador.recibidos == []
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>space"


def test_no_puede_repetir_la_tecla_para_dictar(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    ajustes.establecer("atajo.mantener", "F9")  # la tecla para dictar se cambia en «Dictado»
    pagina.campo_alternar.atajo = "F9"

    pagina.aplicar()

    assert "distint" in pagina.mensaje and aplicador.recibidos == []
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>space"


def test_las_dos_teclas_de_la_pagina_no_pueden_ser_iguales(qtbot: QtBot) -> None:
    pagina, _, aplicador = _pagina(qtbot)
    pagina.campo_alternar.atajo = "Ctrl+Alt+D"
    pagina.campo_traducir.atajo = "Ctrl+Alt+D"

    pagina.aplicar()

    assert "distint" in pagina.mensaje and aplicador.recibidos == []


def test_si_la_escucha_falla_por_otra_razon_se_explica(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    aplicador.error = RuntimeError("esperá a que termine el dictado")
    pagina.campo_alternar.atajo = "Ctrl+Alt+D"

    pagina.aplicar()

    assert "esperá" in pagina.mensaje
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>space"


def test_restablecer_cada_tecla_vuelve_a_fabrica_y_lo_aplica(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.campo_alternar.atajo = "Ctrl+Alt+D"
    pagina.campo_traducir.atajo = "F10"
    pagina.aplicar()
    fila_alternar = pagina.filas["atajo.alternar"]
    fila_traducir = pagina.filas["atajo.traducir"]
    assert (
        fila_alternar.boton_restablecer is not None
        and not fila_alternar.boton_restablecer.isHidden()
    )

    fila_alternar.boton_restablecer.click()
    assert fila_traducir.boton_restablecer is not None
    fila_traducir.boton_restablecer.click()

    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>space"
    assert ajustes.obtener("atajo.traducir") == "RightAlt"
    assert aplicador.recibidos[-1] == {M: "RightCtrl", A: "<Control><Alt>space", T: "RightAlt"}
    assert pagina.campo_alternar.atajo == "<Control><Alt>space"
    assert pagina.campo_traducir.atajo == "RightAlt"


def test_con_las_teclas_de_fabrica_no_hay_restablecer(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert all(
        f.boton_restablecer is not None and f.boton_restablecer.isHidden()
        for f in pagina.filas.values()
    )


def test_aplicar_sin_cambios_no_toca_la_escucha(qtbot: QtBot) -> None:
    pagina, _, aplicador = _pagina(qtbot)

    pagina.aplicar()

    assert aplicador.recibidos == []


# ---- la tecla de traducir (lote 6) ----------------------------------------------------------------------


def test_cambiar_la_de_traducir_se_aplica_en_vivo_y_se_guarda(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.campo_traducir.atajo = "F10"

    pagina.aplicar()

    assert aplicador.recibidos[-1][T] == "F10"
    assert ajustes.obtener("atajo.traducir") == "F10"


def test_la_de_traducir_no_puede_repetir_otra_tecla(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.campo_traducir.atajo = "RightCtrl"  # es la de dictar

    pagina.aplicar()

    assert pagina.hay_error is True and "distint" in pagina.mensaje
    assert aplicador.recibidos == [] and ajustes.obtener("atajo.traducir") == "RightAlt"


def test_si_la_de_traducir_choca_con_otra_funcion_avisa_y_no_guarda(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    aplicador.error = AtajoOcupado("F10 ya lo usa la función «x» de GNOME")
    pagina.campo_traducir.atajo = "F10"

    pagina.aplicar()

    assert pagina.hay_error is True and ajustes.obtener("atajo.traducir") == "RightAlt"


def test_la_de_traducir_acepta_un_modificador_solo(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    _apretar_y_soltar(
        pagina.campo_traducir, Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier, 62
    )  # Shift derecho

    assert pagina.campo_traducir.atajo == "RightShift"


# ---- teclas dibujadas y ayuda (lote 7 y 002) -------------------------------------------------------------


def test_cada_atajo_se_muestra_como_teclas_dibujadas(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.teclas_mostradas("alternar") == ["Ctrl", "Alt", "Espacio"]
    assert pagina.teclas_mostradas("traducir") == ["Alt der."]


def test_las_teclas_dibujadas_siguen_al_campo(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    pagina.campo_traducir.atajo = "F9"

    assert pagina.teclas_mostradas("traducir") == ["F9"]


def test_cada_tecla_lleva_su_titulo_y_su_ayuda_en_lenguaje_llano(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QLabel

    from vozflow.ui.textos import ayuda_de, texto_de

    pagina, _, _ = _pagina(qtbot)
    textos = [e.text() for e in pagina.findChildren(QLabel)]

    for clave in ("atajo.alternar", "atajo.traducir"):
        assert texto_de(clave).titulo in textos and ayuda_de(clave) in textos


def test_estan_las_claves_para_el_inventario() -> None:
    assert PaginaTeclas.CLAVES == ("atajo.alternar", "atajo.traducir")
