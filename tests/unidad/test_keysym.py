"""Conversión de caracteres a keysyms (RF-016: nunca se manda Enter)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from vozflow.insercion.teclas import (
    CONTROL_IZQUIERDO,
    INSERT,
    MAYUSCULA_IZQUIERDA,
    RETURN,
    a_keysym,
    es_escribible,
)


@pytest.mark.parametrize(
    ("caracter", "keysym"),
    [
        ("a", 0x61),
        ("Z", 0x5A),
        (" ", 0x20),
        ("ñ", 0xF1),
        ("Ñ", 0xD1),
        ("á", 0xE1),
        ("é", 0xE9),
        ("ú", 0xFA),
        ("ü", 0xFC),
        ("¿", 0xBF),
        ("¡", 0xA1),
        ("ç", 0xE7),
    ],
)
def test_el_espanol_y_latin_1_usan_su_punto_de_codigo(caracter: str, keysym: int) -> None:
    assert a_keysym(caracter) == keysym


@pytest.mark.parametrize(
    ("caracter", "keysym"),
    [("€", 0x01000000 + 0x20AC), ("—", 0x01000000 + 0x2014), ("😀", 0x01000000 + 0x1F600)],
)
def test_el_resto_de_unicode_usa_la_regla_de_keysyms_unicode(caracter: str, keysym: int) -> None:
    assert a_keysym(caracter) == keysym


@pytest.mark.parametrize("caracter", ["\n", "\r", "\t", "\x00", "\x1b", "\x7f", "\x85"])
def test_los_caracteres_de_control_nunca_se_convierten_en_teclas(caracter: str) -> None:
    assert es_escribible(caracter) is False
    with pytest.raises(ValueError, match="no se escribe"):
        a_keysym(caracter)


def test_un_texto_de_varios_caracteres_no_es_un_caracter() -> None:
    with pytest.raises(ValueError, match="un solo carácter"):
        a_keysym("ab")
    with pytest.raises(ValueError, match="un solo carácter"):
        a_keysym("")


@given(st.characters(blacklist_categories=("Cc", "Cs")))
def test_todo_caracter_imprimible_tiene_un_keysym_que_no_es_enter(caracter: str) -> None:
    keysym = a_keysym(caracter)

    assert keysym > 0
    assert keysym not in (RETURN, 0xFF8D)  # Return y KP_Enter


def test_las_teclas_modificadoras_y_de_pegado_tienen_su_keysym_estandar() -> None:
    assert CONTROL_IZQUIERDO == 0xFFE3
    assert MAYUSCULA_IZQUIERDA == 0xFFE1
    assert INSERT == 0xFF63
    assert RETURN == 0xFF0D
