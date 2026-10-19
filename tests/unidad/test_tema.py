"""El tema visual (guía de diseño de OpenWhispr): paletas, contraste y hoja de estilos."""

import re
from pathlib import Path

import pytest

from vozflow.ui.tema import CLARA, OSCURA, Paleta, contraste, hoja_de_estilos, paleta_del_sistema

PALETAS = [pytest.param(OSCURA, id="oscura"), pytest.param(CLARA, id="clara")]
HEX = re.compile(r"^#[0-9a-f]{6}$")


# ---- contraste -------------------------------------------------------------------------------


def test_el_contraste_de_blanco_sobre_negro_es_21() -> None:
    assert contraste("#ffffff", "#000000") == pytest.approx(21.0)


def test_el_contraste_de_un_color_consigo_mismo_es_1() -> None:
    assert contraste("#3e89ff", "#3e89ff") == pytest.approx(1.0)


def test_el_contraste_no_depende_del_orden() -> None:
    assert contraste("#191b1d", "#e8e8e8") == pytest.approx(contraste("#e8e8e8", "#191b1d"))


# ---- las paletas -------------------------------------------------------------------------------


@pytest.mark.parametrize("paleta", PALETAS)
def test_todos_los_colores_son_hexadecimales_de_seis_cifras(paleta: Paleta) -> None:
    for nombre, valor in vars(paleta).items():
        if nombre != "nombre":
            assert HEX.match(valor), f"{nombre} = {valor}"


def test_la_oscura_usa_los_valores_de_la_guia() -> None:
    assert OSCURA.fondo == "#191b1d" and OSCURA.tarjeta == "#24272a"
    assert OSCURA.texto == "#e8e8e8" and OSCURA.borde == "#383b3e"


def test_la_clara_usa_los_valores_de_la_guia() -> None:
    assert CLARA.superficie == "#ffffff" or CLARA.tarjeta == "#ffffff"
    assert CLARA.borde == "#e3e3e3" and CLARA.texto_atenuado == "#656565"


@pytest.mark.parametrize("paleta", PALETAS)
def test_el_texto_se_lee_sobre_cada_superficie(paleta: Paleta) -> None:
    for fondo in (paleta.fondo, paleta.ventana, paleta.tarjeta, paleta.superficie, paleta.campo):
        assert contraste(paleta.texto, fondo) >= 4.5, (paleta.nombre, fondo)


@pytest.mark.parametrize("paleta", PALETAS)
def test_el_texto_atenuado_se_lee_sobre_el_fondo_y_las_tarjetas(paleta: Paleta) -> None:
    for fondo in (paleta.fondo, paleta.ventana, paleta.tarjeta, paleta.campo):
        assert contraste(paleta.texto_atenuado, fondo) >= 4.5, (paleta.nombre, fondo)


@pytest.mark.parametrize("paleta", PALETAS)
def test_el_texto_del_boton_principal_se_lee_sobre_su_relleno(paleta: Paleta) -> None:
    assert contraste(paleta.texto_sobre_primario, paleta.primario) >= 4.5


@pytest.mark.parametrize("paleta", PALETAS)
def test_los_enlaces_y_el_acento_se_leen_como_texto(paleta: Paleta) -> None:
    for fondo in (paleta.fondo, paleta.tarjeta):
        assert contraste(paleta.enlace, fondo) >= 4.5, (paleta.nombre, "enlace", fondo)
        assert contraste(paleta.acento_texto, fondo) >= 4.5, (paleta.nombre, "acento", fondo)


@pytest.mark.parametrize("paleta", PALETAS)
def test_los_avisos_de_error_se_leen(paleta: Paleta) -> None:
    for fondo in (paleta.fondo, paleta.tarjeta):
        assert contraste(paleta.error, fondo) >= 4.5, (paleta.nombre, fondo)
        assert contraste(paleta.exito, fondo) >= 4.5, (paleta.nombre, fondo)


@pytest.mark.parametrize("paleta", PALETAS)
def test_el_anillo_de_foco_y_el_interruptor_encendido_se_distinguen(paleta: Paleta) -> None:
    for fondo in (paleta.fondo, paleta.tarjeta, paleta.campo):
        assert contraste(paleta.foco, fondo) >= 3.0, (paleta.nombre, "foco", fondo)
    assert contraste(paleta.primario, paleta.tarjeta) >= 3.0


@pytest.mark.parametrize("paleta", PALETAS)
def test_la_tarjeta_se_distingue_del_fondo(paleta: Paleta) -> None:
    assert paleta.tarjeta != paleta.fondo


# ---- elegir tema según el sistema --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("esquema", "esperada"),
    [("dark", OSCURA), ("light", CLARA), ("DARK", OSCURA), ("Light", CLARA)],
)
def test_sigue_el_esquema_de_colores_del_sistema(esquema: str, esperada: Paleta) -> None:
    assert paleta_del_sistema(esquema) is esperada


@pytest.mark.parametrize("esquema", [None, "", "unknown", "raro"])
def test_sin_dato_claro_usa_el_oscuro_como_la_referencia(esquema: str | None) -> None:
    assert paleta_del_sistema(esquema) is OSCURA


# ---- la hoja de estilos ----------------------------------------------------------------------------------


@pytest.mark.parametrize("paleta", PALETAS)
def test_la_hoja_de_estilos_no_deja_marcadores_sin_resolver(paleta: Paleta) -> None:
    hoja = hoja_de_estilos(paleta, "Adwaita Sans")

    assert "{{" not in hoja and "}}" not in hoja and "%(" not in hoja
    assert "None" not in hoja


@pytest.mark.parametrize("paleta", PALETAS)
def test_la_hoja_usa_los_colores_de_la_paleta_y_la_fuente(paleta: Paleta) -> None:
    hoja = hoja_de_estilos(paleta, "Adwaita Sans")

    for color in (paleta.fondo, paleta.tarjeta, paleta.texto, paleta.borde, paleta.primario):
        assert color in hoja
    assert '"Adwaita Sans"' in hoja


@pytest.mark.parametrize("paleta", PALETAS)
def test_la_hoja_cubre_los_controles_que_usa_la_aplicacion(paleta: Paleta) -> None:
    hoja = hoja_de_estilos(paleta, "Adwaita Sans")

    for control in (
        "QPushButton", "QLineEdit", "QPlainTextEdit", "QComboBox", "QSpinBox", "QListWidget",
        "QTableWidget", "QScrollBar", "QToolTip", "QStatusBar", "QMenu", "QCheckBox",
    ):  # fmt: skip
        assert control in hoja, control


def test_el_boton_principal_se_marca_con_una_propiedad() -> None:
    assert 'QPushButton[principal="true"]' in hoja_de_estilos(OSCURA, "x")


def test_la_hoja_es_estable_para_la_misma_entrada() -> None:
    assert hoja_de_estilos(OSCURA, "Inter") == hoja_de_estilos(OSCURA, "Inter")


def test_las_llaves_de_la_hoja_estan_balanceadas() -> None:
    hoja = hoja_de_estilos(CLARA, "Inter")

    assert hoja.count("{") == hoja.count("}")


# ---- los recursos que referencia la hoja ---------------------------------------------------------------


def test_prepara_la_flecha_y_el_tilde_tenidos_con_la_paleta(tmp_path: Path) -> None:
    from vozflow.ui.tema import preparar_recursos

    rutas = preparar_recursos(OSCURA, tmp_path)

    assert set(rutas) == {"flecha", "tilde"}
    assert OSCURA.texto_atenuado in Path(rutas["flecha"]).read_text(encoding="utf-8")
    assert OSCURA.texto_sobre_primario in Path(rutas["tilde"]).read_text(encoding="utf-8")


def test_la_hoja_referencia_los_recursos_cuando_se_le_dan(tmp_path: Path) -> None:
    from vozflow.ui.tema import preparar_recursos

    rutas = preparar_recursos(CLARA, tmp_path)

    hoja = hoja_de_estilos(CLARA, "Inter", rutas)

    assert rutas["flecha"] in hoja and rutas["tilde"] in hoja
    assert hoja.count("{") == hoja.count("}")


def test_los_recursos_de_cada_tema_no_se_pisan(tmp_path: Path) -> None:
    from vozflow.ui.tema import preparar_recursos

    a, b = preparar_recursos(OSCURA, tmp_path), preparar_recursos(CLARA, tmp_path)

    assert a["flecha"] != b["flecha"]


# ---- el acento es un cherry lavado, no el azul de la referencia -----------------------------------------------


@pytest.mark.parametrize("paleta", PALETAS)
def test_el_acento_es_un_cherry_y_no_un_azul(paleta: Paleta) -> None:
    for color in (paleta.primario, paleta.acento, paleta.acento_texto, paleta.foco):
        rojo, verde, azul = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        assert rojo > azul and rojo > verde + 30, (paleta.nombre, color)


@pytest.mark.parametrize("paleta", PALETAS)
def test_el_cherry_es_lavado_y_no_un_rojo_saturado(paleta: Paleta) -> None:
    rojo, verde, azul = (int(paleta.primario[i : i + 2], 16) for i in (1, 3, 5))
    assert verde >= 50 and azul >= 70, paleta.primario  # con algo de gris: apagado


@pytest.mark.parametrize("paleta", PALETAS)
def test_la_seleccion_lleva_el_tinte_del_acento_y_el_texto_se_lee(paleta: Paleta) -> None:
    rojo, verde, azul = (int(paleta.seleccion[i : i + 2], 16) for i in (1, 3, 5))
    assert rojo >= azul and rojo > verde
    assert contraste(paleta.acento_texto, paleta.seleccion) >= 4.5
