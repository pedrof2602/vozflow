"""Página de apariencia de los ajustes: modo automático, claro u oscuro."""

import os

from pytestqt.qtbot import QtBot

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.apariencia import PaginaApariencia

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _pagina(qtbot: QtBot) -> tuple[PaginaApariencia, AjustesRepo, list[str]]:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    aplicados: list[str] = []
    pagina = PaginaApariencia(ajustes, aplicados.append)
    qtbot.addWidget(pagina)
    return pagina, ajustes, aplicados


def test_ofrece_automatico_claro_y_oscuro(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    opciones = [pagina.selector.itemText(i) for i in range(pagina.selector.count())]

    assert opciones == ["Automático (como el sistema)", "Claro", "Oscuro"]
    assert [pagina.selector.itemData(i) for i in range(3)] == ["auto", "claro", "oscuro"]


def test_arranca_en_automatico(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.selector.currentData() == "auto"


def test_muestra_el_modo_guardado(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("interfaz.tema", "oscuro")
    pagina = PaginaApariencia(ajustes, lambda modo: None)
    qtbot.addWidget(pagina)

    assert pagina.selector.currentData() == "oscuro"


def test_elegir_un_modo_lo_guarda_y_lo_aplica_en_el_momento(qtbot: QtBot) -> None:
    pagina, ajustes, aplicados = _pagina(qtbot)

    pagina.selector.setCurrentIndex(1)

    assert ajustes.obtener("interfaz.tema") == "claro"
    assert aplicados == ["claro"]


def test_volver_a_automatico_tambien_se_guarda(qtbot: QtBot) -> None:
    pagina, ajustes, aplicados = _pagina(qtbot)
    pagina.selector.setCurrentIndex(2)

    pagina.selector.setCurrentIndex(0)

    assert ajustes.obtener("interfaz.tema") == "auto" and aplicados == ["oscuro", "auto"]


def test_mostrar_el_modo_guardado_no_lo_vuelve_a_aplicar(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("interfaz.tema", "claro")
    aplicados: list[str] = []

    pagina = PaginaApariencia(ajustes, aplicados.append)
    qtbot.addWidget(pagina)

    assert aplicados == []


def test_la_ventana_incluye_la_pagina_de_apariencia(qtbot: QtBot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from tests.unidad.test_ventana_ajustes import _contexto
    from vozflow.ui.ajustes.ventana import crear_paginas

    paginas = crear_paginas(_contexto(tmp_path), lambda accion: accion())

    for pagina in paginas.values():
        qtbot.addWidget(pagina)  # que Qt las destruya antes de cerrar el intérprete
    assert "Apariencia" in paginas
