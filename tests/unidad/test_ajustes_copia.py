"""Página de copia de seguridad (RF-022): exportar e importar mostrando qué falló."""

import os
from pathlib import Path

from pytestqt.qtbot import QtBot

from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.copia_repo import CopiaRepo
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.ui.ajustes.copia import PaginaCopia

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _pagina(qtbot: QtBot, archivo: Path | None):  # type: ignore[no-untyped-def]
    base = abrir_base(":memory:")
    pagina = PaginaCopia(CopiaRepo(base), elegir_archivo=lambda modo: archivo)
    qtbot.addWidget(pagina)
    return pagina, base


def test_exporta_a_el_archivo_elegido(qtbot: QtBot, tmp_path: Path) -> None:
    destino = tmp_path / "copia.json"
    pagina, base = _pagina(qtbot, destino)
    DiccionarioRepo(base).agregar("SQLAlchemy")

    pagina.exportar()

    assert "SQLAlchemy" in destino.read_text(encoding="utf-8")
    assert pagina.hay_error is False and "copia.json" in pagina.mensaje


def test_cancelar_el_dialogo_no_hace_nada(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot, None)

    pagina.exportar()
    pagina.importar()

    assert pagina.mensaje == "" and pagina.hay_error is False


def test_importa_y_cuenta_lo_que_trajo(qtbot: QtBot, tmp_path: Path) -> None:
    origen = abrir_base(":memory:")
    DiccionarioRepo(origen).agregar("FastAPI")
    archivo = tmp_path / "copia.json"
    CopiaRepo(origen).exportar_a(archivo)
    pagina, base = _pagina(qtbot, archivo)

    pagina.importar()

    assert [e.palabra for e in DiccionarioRepo(base).listar()] == ["FastAPI"]
    assert pagina.hay_error is False and "1 palabras" in pagina.mensaje


def test_si_el_archivo_se_rechaza_dice_cual_entrada_fallo_y_no_cambia_nada(
    qtbot: QtBot, tmp_path: Path
) -> None:
    archivo = tmp_path / "mala.json"
    archivo.write_text(
        '{"formato": "vozflow-copia", "version": 1, "diccionario": '
        '[{"palabra": "bien"}, {"palabra": ""}]}',
        encoding="utf-8",
    )
    pagina, base = _pagina(qtbot, archivo)

    pagina.importar()

    assert pagina.hay_error is True and "diccionario[1]" in pagina.mensaje
    assert DiccionarioRepo(base).listar() == []


def test_una_version_mas_nueva_se_explica(qtbot: QtBot, tmp_path: Path) -> None:
    archivo = tmp_path / "nueva.json"
    archivo.write_text('{"formato": "vozflow-copia", "version": 9}', encoding="utf-8")
    pagina, _ = _pagina(qtbot, archivo)

    pagina.importar()

    assert pagina.hay_error is True and "versión 9" in pagina.mensaje


def test_un_archivo_que_no_existe_o_no_se_puede_leer_se_explica(
    qtbot: QtBot, tmp_path: Path
) -> None:
    pagina, _ = _pagina(qtbot, tmp_path / "no-esta.json")

    pagina.importar()

    assert pagina.hay_error is True and "leer" in pagina.mensaje


def test_un_destino_que_no_se_puede_escribir_se_explica(qtbot: QtBot, tmp_path: Path) -> None:
    pagina, _ = _pagina(qtbot, tmp_path / "no" / "existe" / "copia.json")

    pagina.exportar()

    assert pagina.hay_error is True and "escribir" in pagina.mensaje


def test_aclara_que_no_incluye_historial_ni_claves(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot, None)

    assert "historial" in pagina.aclaracion.text().lower()
    assert "claves" in pagina.aclaracion.text().lower()
