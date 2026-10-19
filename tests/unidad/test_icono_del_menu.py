"""El ícono y la entrada del menú de aplicaciones (002, RP-001)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from vozflow import escritorio
from vozflow.__main__ import CODIGO_OK, main
from vozflow.ui.logo import COLOR_DEL_LOGO, svg_del_logo

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def datos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    return tmp_path / "datos"


def _icono(datos: Path) -> Path:
    return datos / "icons" / "hicolor" / "scalable" / "apps" / "vozflow.svg"


# ---- el SVG --------------------------------------------------------------------------------------------------


def test_el_logo_se_puede_generar_como_svg_valido() -> None:
    raiz = ET.fromstring(svg_del_logo())

    assert raiz.tag.endswith("svg") and raiz.attrib["viewBox"] == "0 0 256 256"


def test_el_svg_usa_el_color_del_logo_y_barras_blancas() -> None:
    svg = svg_del_logo()

    assert COLOR_DEL_LOGO in svg and "#ffffff" in svg


def test_el_svg_tiene_las_cinco_barras_y_el_fondo_redondeado() -> None:
    raiz = ET.fromstring(svg_del_logo())
    rectangulos = [e for e in raiz.iter() if e.tag.endswith("rect")]

    assert len(rectangulos) == 6  # el fondo y las cinco barras
    assert rectangulos[0].attrib.get("rx")


def test_el_archivo_versionado_coincide_con_el_logo_del_programa() -> None:
    versionado = (RAIZ / "assets" / "vozflow.svg").read_text(encoding="utf-8")

    assert versionado == svg_del_logo()


# ---- instalar y retirar el ícono -------------------------------------------------------------------------


def test_instala_el_icono_en_la_carpeta_xdg(datos: Path) -> None:
    ruta = escritorio.asegurar_icono()

    assert ruta == _icono(datos) and ruta.read_text(encoding="utf-8") == svg_del_logo()


def test_instalar_el_icono_dos_veces_da_lo_mismo(datos: Path) -> None:
    escritorio.asegurar_icono()
    primero = _icono(datos).read_text(encoding="utf-8")

    escritorio.asegurar_icono()

    assert _icono(datos).read_text(encoding="utf-8") == primero


def test_un_icono_ajeno_con_el_mismo_nombre_no_se_pisa(datos: Path) -> None:
    ruta = _icono(datos)
    ruta.parent.mkdir(parents=True)
    ruta.write_text("<svg>de otra persona</svg>", encoding="utf-8")

    escritorio.asegurar_icono()

    assert ruta.read_text(encoding="utf-8") == "<svg>de otra persona</svg>"


def test_retirar_el_icono_solo_borra_el_que_genero_vozflow(datos: Path) -> None:
    escritorio.asegurar_icono()
    assert escritorio.retirar_icono() is True and not _icono(datos).exists()

    ruta = _icono(datos)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("<svg>ajeno</svg>", encoding="utf-8")
    assert escritorio.retirar_icono() is False and ruta.exists()


# ---- la entrada visible del menú ----------------------------------------------------------------------------


def test_la_entrada_del_menu_es_visible_y_lleva_el_icono(datos: Path) -> None:
    ruta = escritorio.asegurar_entrada_de_escritorio(
        ruta_uv="/usr/bin/uv", proyecto=Path("/proyectos/vozflow")
    )
    texto = ruta.read_text(encoding="utf-8")

    assert "Icon=vozflow" in texto and "NoDisplay" not in texto
    assert "Name=vozflow" in texto and "Comment=Dictado por voz local" in texto
    assert "Categories=Utility;" in texto and "Terminal=false" in texto


def test_una_entrada_vieja_oculta_se_actualiza_a_la_visible(datos: Path) -> None:
    ruta = escritorio.ruta_de_la_entrada()
    ruta.parent.mkdir(parents=True)
    ruta.write_text("[Desktop Entry]\nNoDisplay=true\nX-Vozflow-Generado=true\n", encoding="utf-8")

    escritorio.asegurar_entrada_de_escritorio(ruta_uv="/usr/bin/uv", proyecto=Path("/p"))

    assert "NoDisplay" not in ruta.read_text(encoding="utf-8")


# ---- el comando ``entrada`` ----------------------------------------------------------------------------------


def test_el_comando_entrada_instalar_crea_la_entrada_y_el_icono(
    datos: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.dobles import MotorFalso
    from tests.unidad.test_cli_dictar import GrabadoraFalsa, _dependencias

    codigo = main(["entrada", "instalar"], _dependencias(GrabadoraFalsa(), MotorFalso()))

    assert codigo == CODIGO_OK
    assert escritorio.ruta_de_la_entrada().is_file() and _icono(datos).is_file()
    assert "menú" in capsys.readouterr().out.lower()


def test_instalar_la_entrada_dos_veces_no_duplica_nada(datos: Path) -> None:
    from tests.dobles import MotorFalso
    from tests.unidad.test_cli_dictar import GrabadoraFalsa, _dependencias

    dependencias = _dependencias(GrabadoraFalsa(), MotorFalso())
    main(["entrada", "instalar"], dependencias)
    entrada = escritorio.ruta_de_la_entrada().read_text(encoding="utf-8")

    main(["entrada", "instalar"], dependencias)

    assert escritorio.ruta_de_la_entrada().read_text(encoding="utf-8") == entrada
    assert sorted(p.name for p in escritorio.ruta_de_la_entrada().parent.iterdir()) == [
        "vozflow.desktop"
    ]


def test_el_comando_entrada_retirar_borra_las_dos_cosas(datos: Path) -> None:
    from tests.dobles import MotorFalso
    from tests.unidad.test_cli_dictar import GrabadoraFalsa, _dependencias

    dependencias = _dependencias(GrabadoraFalsa(), MotorFalso())
    main(["entrada", "instalar"], dependencias)

    codigo = main(["entrada", "retirar"], dependencias)

    assert codigo == CODIGO_OK
    assert not escritorio.ruta_de_la_entrada().exists() and not _icono(datos).exists()
