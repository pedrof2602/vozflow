"""Cómo se inserta un texto: pegado con teclas y nunca un Enter (RF-015 a RF-017)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from vozflow.dominio.pegado import decidir_estrategia, teclas_para_escribir
from vozflow.insercion.puerto import AtajoDePegado, Destino

RETURN, KP_ENTER = 0xFF0D, 0xFF8D
CTRL, SHIFT, INSERT, V = 0xFFE3, 0xFFE1, 0xFF63, 0x76


def test_por_defecto_se_pega_con_shift_insert_y_se_copia_a_la_primaria() -> None:
    estrategia = decidir_estrategia("hola", Destino())

    assert estrategia.atajo is AtajoDePegado.SHIFT_INSERT
    assert estrategia.teclas == (SHIFT, INSERT)
    assert estrategia.texto == "hola"
    assert estrategia.copiar_a_primaria is True


@pytest.mark.parametrize(
    ("atajo", "teclas"),
    [
        (AtajoDePegado.SHIFT_INSERT, (SHIFT, INSERT)),
        (AtajoDePegado.CTRL_V, (CTRL, V)),
        (AtajoDePegado.CTRL_SHIFT_V, (CTRL, SHIFT, V)),
    ],
)
def test_una_aplicacion_marcada_usa_su_propio_atajo(
    atajo: AtajoDePegado, teclas: tuple[int, ...]
) -> None:
    assert decidir_estrategia("hola", Destino(atajo=atajo)).teclas == teclas


def test_con_salto_de_linea_conservar_el_texto_queda_igual() -> None:
    assert decidir_estrategia("a\nb", Destino()).texto == "a\nb"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("a\nb", "a b"), ("a\r\nb", "a b"), ("a\n\nb", "a b"), ("a\nb\nc", "a b c"), ("a \nb", "a b")],
)
def test_con_salto_de_linea_espacio_se_reemplaza_por_un_espacio(texto: str, esperado: str) -> None:
    assert decidir_estrategia(texto, Destino(salto_de_linea="espacio")).texto == esperado


def test_un_texto_de_una_linea_se_puede_escribir_por_keysyms() -> None:
    teclas = teclas_para_escribir("sí ñ")

    assert teclas == (0x73, 0xED, 0x20, 0xF1)


@pytest.mark.parametrize("texto", ["a\nb", "a\rb", "a\tb", "\x1b"])
def test_lo_que_tiene_saltos_o_control_no_se_escribe_por_teclas(texto: str) -> None:
    assert teclas_para_escribir(texto) is None


def test_un_texto_vacio_no_tiene_nada_que_escribir() -> None:
    assert teclas_para_escribir("") == ()


# ---- RF-016: nunca un Enter -------------------------------------------------------------------


@given(
    texto=st.text(),
    atajo=st.sampled_from(AtajoDePegado),
    salto=st.sampled_from(["conservar", "espacio"]),
)
def test_ninguna_secuencia_de_teclas_contiene_return_ni_enter_del_teclado_numerico(
    texto: str, atajo: AtajoDePegado, salto: str
) -> None:
    estrategia = decidir_estrategia(texto, Destino(atajo=atajo, salto_de_linea=salto))  # type: ignore[arg-type]
    escritas = teclas_para_escribir(estrategia.texto) or ()

    for tecla in (*estrategia.teclas, *escritas):
        assert tecla not in (RETURN, KP_ENTER)


@given(st.text())
def test_con_salto_espacio_no_queda_ningun_salto_en_el_texto(texto: str) -> None:
    resultado = decidir_estrategia(texto, Destino(salto_de_linea="espacio")).texto

    assert "\n" not in resultado and "\r" not in resultado
