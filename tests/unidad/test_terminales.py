"""Qué aplicaciones son terminales (importa para el modo «Terminal» de un dictado)."""

import pytest

from vozflow.dominio.terminales import es_terminal


@pytest.mark.parametrize(
    "aplicacion",
    [
        "ptyxis",
        "konsole",
        "gnome-terminal",
        "gnome-terminal-server",
        "kitty",
        "alacritty",
        "wezterm",
        "foot",
        "tilix",
        "xterm",
        "terminator",
        "org.gnome.console",
        "kgx",
    ],
)
def test_reconoce_los_emuladores_de_terminal_conocidos(aplicacion: str) -> None:
    assert es_terminal(aplicacion) is True


@pytest.mark.parametrize(
    ("aplicacion"),
    [
        "org.gnome.Ptyxis",
        "Ptyxis",
        "KONSOLE",
        "  kitty ",
        "org.wezfurlong.wezterm",
        "com.mitchellh.ghostty",
    ],
)
def test_ignora_mayusculas_espacios_y_el_prefijo_del_identificador_de_aplicacion(
    aplicacion: str,
) -> None:
    assert es_terminal(aplicacion) is True


@pytest.mark.parametrize(
    "aplicacion",
    [
        "google chrome",
        "chrome",
        "firefox",
        "code",
        "obsidian",
        "teams",
        "gedit",
        "nautilus",
        "",
        "ptyxis-no",
    ],
)
def test_lo_que_no_es_una_terminal_no_lo_es(aplicacion: str) -> None:
    assert es_terminal(aplicacion) is False


def test_una_aplicacion_marcada_a_mano_como_terminal_lo_es() -> None:
    assert es_terminal("vscodium", marcadas={"vscodium"}) is True
    assert es_terminal("VSCodium", marcadas={"vscodium"}) is True


def test_la_marca_manual_de_una_aplicacion_no_afecta_a_las_demas() -> None:
    assert es_terminal("firefox", marcadas={"vscodium"}) is False


def test_sin_aplicacion_conocida_no_es_terminal() -> None:
    assert es_terminal("") is False
    assert es_terminal("", marcadas={""}) is False
