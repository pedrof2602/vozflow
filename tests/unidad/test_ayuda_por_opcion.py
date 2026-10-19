"""Cada opción se explica y los valores de fábrica ya dictan bien (002, RP-017, RP-018)."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from tests.unidad.test_ventana_ajustes import _contexto
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.ventana import crear_paginas
from vozflow.ui.componentes import FilaDeAjuste
from vozflow.ui.textos import TEXTOS, ayuda_de, texto_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def paginas(qtbot: QtBot, tmp_path: Path) -> dict[str, QWidget]:
    creadas = crear_paginas(_contexto(tmp_path), lambda accion: accion())
    for pagina in creadas.values():
        qtbot.addWidget(pagina)
    return creadas


def test_toda_fila_de_ajuste_tiene_titulo_y_ayuda(paginas: dict[str, QWidget]) -> None:
    filas = [f for p in paginas.values() for f in p.findChildren(FilaDeAjuste)]

    assert filas  # hay filas que revisar
    for fila in filas:
        assert fila.titulo.strip() and fila.ayuda.strip(), fila.titulo


def test_la_ayuda_de_cada_fila_es_la_del_archivo_de_textos(paginas: dict[str, QWidget]) -> None:
    ayudas = {t.ayuda for t in TEXTOS.values()}

    for pagina in paginas.values():
        for fila in pagina.findChildren(FilaDeAjuste):
            assert fila.ayuda in ayudas, fila.titulo


# (página, atributo, clave de textos): los controles de «Avanzado» que no son filas llevan su ayuda
# como pista al pasar el ratón.
CON_PISTA = [
    ("Modos", "check_muletillas", "modo.muletillas"),
    ("Modos", "check_puntuacion", "modo.puntuacion"),
    ("Modos", "check_comandos", "modo.comandos"),
    ("Modos", "campo_instruccion", "modo.estilo"),
    ("Modos", "combo_pegado", "modo.pegado"),
    ("Modos", "combo_salto", "modo.saltos"),
    ("Modos", "check_terminal", "modo.terminal"),
    ("Copia de seguridad", "boton_exportar", "copia.exportar"),
    ("Copia de seguridad", "boton_importar", "copia.importar"),
]


@pytest.mark.parametrize(("pagina", "atributo", "clave"), CON_PISTA)
def test_los_controles_tecnicos_llevan_su_ayuda_como_pista(
    paginas: dict[str, QWidget], pagina: str, atributo: str, clave: str
) -> None:
    control = getattr(paginas[pagina], atributo)

    assert control.toolTip() == ayuda_de(clave)


def test_los_titulos_de_modos_salen_del_archivo_de_textos(paginas: dict[str, QWidget]) -> None:
    modos = paginas["Modos"]

    assert modos.check_muletillas.text() == texto_de("modo.muletillas").titulo  # type: ignore[attr-defined]
    assert modos.check_terminal.text() == texto_de("modo.terminal").titulo  # type: ignore[attr-defined]


def test_con_una_base_nueva_los_valores_de_fabrica_dictan_bien() -> None:
    ajustes = AjustesRepo(abrir_base(":memory:")).cargar()

    assert ajustes.atajo_mantener == "RightCtrl" and ajustes.atajo_alternar == "<Control><Alt>space"
    assert ajustes.modelo == "small" and ajustes.hilos == 4 and ajustes.idioma is None
    assert ajustes.historial_activo is True and ajustes.indicador is True
    assert ajustes.reescritura_activa is False  # nada sale del equipo sin que lo prendas
