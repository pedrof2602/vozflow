"""El atajo de GNOME (línea base del modo alternar): se registra con ``gsettings`` y llama por D-Bus."""

import pytest

from tests.dobles import GSettingsFalso
from vozflow.atajos.gsettings import (
    COMANDO,
    ESQUEMA_DE_LA_LISTA,
    RUTA_PROPIA,
    AtajoDeGnome,
    ErrorDeGSettings,
    a_formato_gnome,
    leer_lista,
)
from vozflow.atajos.puerto import AtajoOcupado

ESQUEMA_PROPIO = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{RUTA_PROPIA}"
OTRA_RUTA = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/otra/"
ESQUEMA_OTRA = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{OTRA_RUTA}"


def _gnome(falso: GSettingsFalso) -> AtajoDeGnome:
    return AtajoDeGnome(ejecutar=falso)


# ---- formato de las teclas ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Ctrl+Alt+Space", "<Control><Alt>space"),
        ("<Control><Alt>space", "<Control><Alt>space"),
        ("CTRL+ALT+d", "<Control><Alt>d"),
        ("F9", "F9"),
        ("f12", "F12"),
        ("<Super>d", "<Super>d"),
        ("Shift+Control+7", "<Shift><Control>7"),
        ("<Control>ScrollLock", "<Control>Scroll_Lock"),
        ("Ctrl+Insert", "<Control>Insert"),
    ],
)
def test_convierte_el_nombre_al_formato_que_usa_gnome(entrada: str, esperado: str) -> None:
    assert a_formato_gnome(entrada) == esperado


@pytest.mark.parametrize("entrada", ["RightCtrl", "", "Ctrl", "Ctrl+Alt"])
def test_lo_que_no_es_un_atajo_de_gnome_se_rechaza(entrada: str) -> None:
    with pytest.raises(ValueError, match="atajo|tecla|modificador"):
        a_formato_gnome(entrada)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("@as []", []),
        ("[]", []),
        ("['/a/']", ["/a/"]),
        ("['/a/', '/b/']", ["/a/", "/b/"]),
    ],
)
def test_lee_la_lista_en_el_formato_de_gsettings(texto: str, esperado: list[str]) -> None:
    falso = GSettingsFalso()
    falso.precargar(ESQUEMA_DE_LA_LISTA, "custom-keybindings", texto)

    assert leer_lista(falso) == esperado


# ---- registrar ------------------------------------------------------------------------------------


def test_registra_el_atajo_con_su_nombre_comando_y_tecla() -> None:
    falso = GSettingsFalso()

    _gnome(falso).registrar("<Control><Alt>space")

    assert leer_lista(falso) == [RUTA_PROPIA]
    assert falso.valores[(ESQUEMA_PROPIO, "name")] == "'vozflow'"
    assert falso.valores[(ESQUEMA_PROPIO, "binding")] == "'<Control><Alt>space'"
    assert falso.valores[(ESQUEMA_PROPIO, "command")] == repr(COMANDO)


def test_el_comando_llama_al_servicio_de_vozflow_por_dbus() -> None:
    assert COMANDO == (
        "dbus-send --session --type=method_call --dest=com.vozflow.App "
        "/com/vozflow/App com.vozflow.App.Toggle"
    )


def test_agrega_sin_pisar_los_atajos_de_otras_aplicaciones() -> None:
    falso = GSettingsFalso()
    falso.precargar(ESQUEMA_DE_LA_LISTA, "custom-keybindings", f"['{OTRA_RUTA}']")
    falso.precargar(ESQUEMA_OTRA, "binding", "'<Super>t'")
    falso.precargar(ESQUEMA_OTRA, "name", "'terminal'")

    _gnome(falso).registrar("<Control><Alt>space")

    assert leer_lista(falso) == [OTRA_RUTA, RUTA_PROPIA]
    assert falso.valores[(ESQUEMA_OTRA, "binding")] == "'<Super>t'"


def test_registrar_dos_veces_no_duplica_la_entrada() -> None:
    falso = GSettingsFalso()

    _gnome(falso).registrar("<Control><Alt>space")
    _gnome(falso).registrar("<Control><Alt>space")

    assert leer_lista(falso) == [RUTA_PROPIA]


def test_una_entrada_propia_que_quedo_de_una_ejecucion_anterior_no_es_un_choque() -> None:
    falso = GSettingsFalso()
    falso.precargar(ESQUEMA_DE_LA_LISTA, "custom-keybindings", f"['{RUTA_PROPIA}']")
    falso.precargar(ESQUEMA_PROPIO, "binding", "'<Control><Alt>space'")

    _gnome(falso).registrar("<Control><Alt>space")  # no lanza

    assert leer_lista(falso) == [RUTA_PROPIA]


# ---- choques con otras funciones (RF-003) ------------------------------------------------------------------


def test_otro_atajo_personalizado_con_la_misma_tecla_es_un_choque() -> None:
    falso = GSettingsFalso()
    falso.precargar(ESQUEMA_DE_LA_LISTA, "custom-keybindings", f"['{OTRA_RUTA}']")
    falso.precargar(ESQUEMA_OTRA, "binding", "'<Control><Alt>space'")
    falso.precargar(ESQUEMA_OTRA, "name", "'mi grabadora'")

    with pytest.raises(AtajoOcupado, match="mi grabadora"):
        _gnome(falso).registrar("<Control><Alt>space")

    assert leer_lista(falso) == [OTRA_RUTA]  # no se tocó nada


def test_un_atajo_propio_de_gnome_con_la_misma_tecla_es_un_choque() -> None:
    falso = GSettingsFalso()
    falso.precargar("org.gnome.desktop.wm.keybindings", "activate-window-menu", "['<Alt>space']")

    with pytest.raises(AtajoOcupado, match=r"activate-window-menu"):
        _gnome(falso).registrar("<Alt>space")


def test_el_choque_no_depende_del_orden_de_los_modificadores_ni_de_las_mayusculas() -> None:
    falso = GSettingsFalso()
    falso.precargar("org.gnome.shell.keybindings", "toggle-overview", "['<Control><Alt>Space']")

    with pytest.raises(AtajoOcupado):
        _gnome(falso).registrar("<Alt><Control>space")


def test_los_valores_vacios_de_gnome_no_son_choques() -> None:
    falso = GSettingsFalso()
    falso.precargar("org.gnome.desktop.wm.keybindings", "always-on-top", "@as []")
    falso.precargar("org.gnome.settings-daemon.plugins.media-keys", "home", "['']")

    _gnome(falso).registrar("<Control><Alt>space")  # no lanza


def test_una_tecla_distinta_no_choca() -> None:
    falso = GSettingsFalso()
    falso.precargar("org.gnome.desktop.wm.keybindings", "close", "['<Alt>F4']")

    _gnome(falso).registrar("<Control><Alt>space")


# ---- quitar --------------------------------------------------------------------------------------------------------


def test_quitar_borra_solo_la_entrada_propia() -> None:
    falso = GSettingsFalso()
    falso.precargar(ESQUEMA_DE_LA_LISTA, "custom-keybindings", f"['{OTRA_RUTA}']")
    gnome = _gnome(falso)
    gnome.registrar("<Control><Alt>space")

    gnome.quitar()

    assert leer_lista(falso) == [OTRA_RUTA]
    assert not [k for k in falso.valores if k[0] == ESQUEMA_PROPIO]


def test_quitar_sin_haber_registrado_no_hace_nada() -> None:
    falso = GSettingsFalso()

    _gnome(falso).quitar()

    assert leer_lista(falso) == []


def test_quitar_dos_veces_es_inofensivo() -> None:
    falso = GSettingsFalso()
    gnome = _gnome(falso)
    gnome.registrar("<Control><Alt>space")

    gnome.quitar()
    gnome.quitar()

    assert leer_lista(falso) == []


# ---- gsettings no disponible ------------------------------------------------------------------------------------------


def test_si_gsettings_no_existe_se_explica() -> None:
    falso = GSettingsFalso()
    falso.fallar_con = FileNotFoundError("gsettings")

    with pytest.raises(ErrorDeGSettings, match="gsettings"):
        _gnome(falso).registrar("<Control><Alt>space")
