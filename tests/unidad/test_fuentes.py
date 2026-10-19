"""La tipografía: la primera de la lista que exista (sin empaquetar fuentes)."""

import pytest

from vozflow.ui.fuentes import FAMILIAS_PREFERIDAS, elegir_familia


def test_la_lista_prefiere_inter_y_su_derivada_de_gnome() -> None:
    assert FAMILIAS_PREFERIDAS[:2] == ("Inter", "Adwaita Sans")
    assert "Noto Sans" in FAMILIAS_PREFERIDAS and "Cantarell" in FAMILIAS_PREFERIDAS


def test_elige_la_primera_preferida_que_existe() -> None:
    assert elegir_familia(["Cantarell", "Adwaita Sans", "DejaVu Sans"]) == "Adwaita Sans"


def test_si_estan_todas_gana_inter() -> None:
    assert elegir_familia(["Noto Sans", "Inter", "Cantarell", "Adwaita Sans"]) == "Inter"


def test_no_distingue_mayusculas() -> None:
    assert elegir_familia(["adwaita sans"]) == "Adwaita Sans"


def test_devuelve_el_nombre_tal_como_lo_conoce_la_preferida() -> None:
    assert elegir_familia(["NOTO SANS"]) == "Noto Sans"


def test_si_no_hay_ninguna_cae_a_la_generica_del_sistema() -> None:
    assert elegir_familia(["Comic Neue", "Papyrus"]) == "sans-serif"
    assert elegir_familia([]) == "sans-serif"


@pytest.mark.parametrize("disponibles", [["Inter"], ["Inter Display", "Cantarell"]])
def test_no_confunde_una_familia_parecida_con_la_preferida(disponibles: list[str]) -> None:
    resultado = elegir_familia(disponibles)

    assert resultado in ("Inter", "Cantarell")
    assert not (disponibles == ["Inter Display", "Cantarell"] and resultado == "Inter")


def test_con_qt_encuentra_una_familia_instalada() -> None:
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from vozflow.ui.fuentes import familia_del_sistema

    app = QApplication.instance() or QApplication([])
    resultado = familia_del_sistema()

    assert resultado == "sans-serif" or resultado in QFontDatabase.families()
    assert app is not None
