"""Página de sistema de los ajustes: arrancar con la sesión, con un clic."""

import os

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from vozflow.ui.ajustes.sistema import PaginaSistema

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


def _pagina(qtbot: QtBot, autoinicio: Autoinicio) -> PaginaSistema:
    pagina = PaginaSistema(autoinicio.leer, autoinicio.fijar)
    qtbot.addWidget(pagina)
    pagina.show()
    return pagina


def test_el_interruptor_refleja_si_el_arranque_esta_activo(qtbot: QtBot) -> None:
    assert _pagina(qtbot, Autoinicio(True)).interruptor.isChecked() is True
    assert _pagina(qtbot, Autoinicio(False)).interruptor.isChecked() is False


def test_un_clic_activa_el_arranque_en_segundo_plano(qtbot: QtBot) -> None:
    autoinicio = Autoinicio(False)
    pagina = _pagina(qtbot, autoinicio)

    QTest.mouseClick(pagina.interruptor, Qt.MouseButton.LeftButton)

    assert autoinicio.activo is True and autoinicio.llamadas == [True]
    assert pagina.hay_error is False and "arrancará" in pagina.mensaje


def test_otro_clic_lo_desactiva(qtbot: QtBot) -> None:
    autoinicio = Autoinicio(True)
    pagina = _pagina(qtbot, autoinicio)

    QTest.mouseClick(pagina.interruptor, Qt.MouseButton.LeftButton)

    assert autoinicio.activo is False and autoinicio.llamadas == [False]
    assert "ya no arranca" in pagina.mensaje


def test_si_no_se_puede_el_interruptor_vuelve_atras_y_explica(qtbot: QtBot) -> None:
    autoinicio = Autoinicio(
        False, falla=FileExistsError("ya existe un archivo que no es de vozflow")
    )
    pagina = _pagina(qtbot, autoinicio)

    QTest.mouseClick(pagina.interruptor, Qt.MouseButton.LeftButton)

    assert pagina.interruptor.isChecked() is False
    assert pagina.hay_error is True and "ya existe" in pagina.mensaje


def test_el_error_al_volver_atras_no_dispara_otro_cambio(qtbot: QtBot) -> None:
    autoinicio = Autoinicio(False, falla=OSError("sin permiso"))
    pagina = _pagina(qtbot, autoinicio)

    QTest.mouseClick(pagina.interruptor, Qt.MouseButton.LeftButton)

    assert autoinicio.llamadas == [True]


def test_la_pagina_explica_que_es_arrancar_en_segundo_plano(qtbot: QtBot) -> None:
    pagina = _pagina(qtbot, Autoinicio())

    textos = " ".join(e.text() for e in pagina.findChildren(type(pagina._etiqueta_mensaje)))

    assert "segundo plano" in textos


def test_la_ventana_incluye_la_pagina_sistema(qtbot: QtBot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from tests.unidad.test_ventana_ajustes import _contexto
    from vozflow.ui.ajustes.ventana import crear_paginas

    paginas = crear_paginas(_contexto(tmp_path), lambda accion: accion())
    for pagina in paginas.values():
        qtbot.addWidget(pagina)

    assert "Sistema" in paginas
