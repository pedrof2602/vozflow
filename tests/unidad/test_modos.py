"""Resolver el modo de una aplicación y de ahí las opciones y el destino del dictado."""

import pytest

from vozflow.dominio.modos import Asignacion, Modo, resolver
from vozflow.insercion.puerto import AtajoDePegado

GENERAL = Modo(1, "General", es_general=True)
TERMINAL = Modo(2, "Terminal", tipo_pegado="terminal", salto_de_linea="espacio")
CODIGO = Modo(3, "Código", puntuacion_automatica=False)
NORMAL = Modo(4, "Notas", tipo_pegado="normal", salto_de_linea="conservar")
MODOS = [GENERAL, TERMINAL, CODIGO, NORMAL]


def _resolver(aplicacion: str | None, asignaciones: list[Asignacion] | None = None):  # type: ignore[no-untyped-def]
    return resolver(aplicacion, asignaciones or [], MODOS)


def test_una_aplicacion_asignada_usa_su_modo() -> None:
    r = _resolver("code", [Asignacion("code", 3)])

    assert r.modo is CODIGO


def test_sin_asignacion_usa_el_general() -> None:
    assert _resolver("chrome", [Asignacion("code", 3)]).modo is GENERAL


def test_sin_saber_la_aplicacion_usa_el_general() -> None:
    assert _resolver(None).modo is GENERAL
    assert _resolver("").modo is GENERAL


def test_no_distingue_mayusculas_en_el_identificador() -> None:
    assert _resolver("CODE", [Asignacion("code", 3)]).modo is CODIGO


def test_una_asignacion_a_un_modo_que_ya_no_existe_cae_al_general() -> None:
    assert _resolver("code", [Asignacion("code", 99)]).modo is GENERAL


def test_las_banderas_del_modo_pasan_a_las_opciones_de_la_tuberia() -> None:
    r = _resolver("code", [Asignacion("code", 3)])

    assert r.opciones.puntuacion_automatica is False
    assert r.opciones.quitar_muletillas is True and r.opciones.comandos_de_voz is True


# ---- tipo de pegado --------------------------------------------------------------------------------


def test_el_modo_terminal_pega_con_ctrl_shift_v_y_en_una_linea() -> None:
    r = _resolver("ptyxis", [Asignacion("ptyxis", 2)])

    assert r.destino.atajo is AtajoDePegado.CTRL_SHIFT_V
    assert r.destino.salto_de_linea == "espacio"


def test_el_modo_normal_pega_con_el_atajo_universal() -> None:
    r = _resolver("obsidian", [Asignacion("obsidian", 4)])

    assert r.destino.atajo is AtajoDePegado.SHIFT_INSERT
    assert r.destino.salto_de_linea == "conservar"


def test_automatico_reconoce_una_terminal_conocida() -> None:
    r = _resolver("ptyxis")

    assert r.es_terminal is True
    assert r.destino.atajo is AtajoDePegado.CTRL_SHIFT_V


def test_automatico_no_toma_por_terminal_lo_que_no_lo_es() -> None:
    r = _resolver("obsidian")

    assert r.es_terminal is False
    assert r.destino.atajo is AtajoDePegado.SHIFT_INSERT


def test_automatico_respeta_la_marca_manual_de_terminal() -> None:
    r = _resolver("vscodium", [Asignacion("vscodium", 1, es_terminal=True)])

    assert r.es_terminal is True


def test_una_terminal_nunca_recibe_saltos_de_linea_aunque_el_modo_los_conserve() -> None:
    r = _resolver("ptyxis")  # modo general: conservar

    assert r.modo.salto_de_linea == "conservar"
    assert r.destino.salto_de_linea == "espacio"


@pytest.mark.parametrize("aplicacion", ["org.gnome.Ptyxis", "KONSOLE"])
def test_reconoce_los_identificadores_de_terminal_de_las_distintas_formas(
    aplicacion: str,
) -> None:
    assert _resolver(aplicacion).es_terminal is True


def test_si_no_hay_modo_general_se_avisa() -> None:
    with pytest.raises(LookupError, match="general"):
        resolver("x", [], [TERMINAL])
