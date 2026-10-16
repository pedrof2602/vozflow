"""La entrada ``vozflow.desktop``: sin ella el portal no deja registrar la aplicación."""

import configparser
import logging
from pathlib import Path

import pytest

from vozflow import escritorio


class _Parser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr  # conserva las mayúsculas de las claves


def _leer(ruta: Path) -> configparser.ConfigParser:
    parser = _Parser(interpolation=None)
    parser.read(ruta, encoding="utf-8")
    return parser


@pytest.fixture
def datos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    return tmp_path / "datos"


def _crear(**argumentos: object) -> Path:
    return escritorio.asegurar_entrada_de_escritorio(
        ruta_uv="/usr/bin/uv",
        proyecto=Path("/proyectos/vozflow"),
        **argumentos,
    )


def test_crea_la_entrada_en_la_carpeta_de_aplicaciones_xdg(datos: Path) -> None:
    ruta = _crear()

    assert ruta == datos / "applications" / "vozflow.desktop"
    assert ruta.is_file()


def test_usa_la_carpeta_por_defecto_del_home_sin_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert _crear() == tmp_path / ".local" / "share" / "applications" / "vozflow.desktop"


def test_la_entrada_tiene_lo_que_el_portal_y_el_escritorio_necesitan(datos: Path) -> None:
    entrada = _leer(_crear())["Desktop Entry"]

    assert entrada["Type"] == "Application"
    assert entrada["Name"] == "vozflow"
    assert entrada["NoDisplay"] == "true"
    assert entrada["Terminal"] == "false"
    assert entrada["Exec"] == "/usr/bin/uv run --project /proyectos/vozflow python -m vozflow"


def test_las_rutas_con_espacios_se_entrecomillan_en_exec(datos: Path) -> None:
    ruta = escritorio.asegurar_entrada_de_escritorio(
        ruta_uv="/opt/mi uv/uv", proyecto=Path("/mis proyectos/vozflow")
    )

    exec_ = _leer(ruta)["Desktop Entry"]["Exec"]
    assert exec_ == '"/opt/mi uv/uv" run --project "/mis proyectos/vozflow" python -m vozflow'


def test_es_legible_para_todos_y_no_ejecutable(datos: Path) -> None:
    assert _crear().stat().st_mode & 0o777 == 0o644


def test_si_ya_esta_igual_no_se_vuelve_a_escribir(datos: Path) -> None:
    ruta = _crear()
    antes = ruta.stat().st_mtime_ns

    _crear()

    assert ruta.stat().st_mtime_ns == antes


def test_si_cambio_la_ruta_se_actualiza(datos: Path) -> None:
    ruta = _crear()

    escritorio.asegurar_entrada_de_escritorio(
        ruta_uv="/usr/local/bin/uv", proyecto=Path("/proyectos/vozflow")
    )

    assert _leer(ruta)["Desktop Entry"]["Exec"].startswith("/usr/local/bin/uv run")


def test_no_pisa_un_archivo_que_no_genero_este_programa(
    datos: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ajeno = datos / "applications" / "vozflow.desktop"
    ajeno.parent.mkdir(parents=True)
    ajeno.write_text("[Desktop Entry]\nName=otra cosa\n")

    with caplog.at_level(logging.WARNING):
        ruta = _crear()

    assert ruta == ajeno
    assert ajeno.read_text() == "[Desktop Entry]\nName=otra cosa\n"
    assert "no lo generó vozflow" in caplog.text


def test_retirar_borra_solo_la_entrada_propia(datos: Path) -> None:
    ruta = _crear()

    assert escritorio.retirar_entrada_de_escritorio() is True
    assert not ruta.exists()
    assert escritorio.retirar_entrada_de_escritorio() is False  # ya no estaba


def test_retirar_no_borra_un_archivo_ajeno(datos: Path) -> None:
    ajeno = datos / "applications" / "vozflow.desktop"
    ajeno.parent.mkdir(parents=True)
    ajeno.write_text("[Desktop Entry]\nName=otra cosa\n")

    assert escritorio.retirar_entrada_de_escritorio() is False
    assert ajeno.exists()
