"""El catálogo de mensajes llanos (``contracts/mensajes.md``, RP-022)."""

import re

import pytest

from vozflow.mensajes import CODIGOS, GENERICO, Explicacion, explicar

ESPERADOS = {
    "pegado_fallo",
    "sin_portapapeles",
    "sin_permiso_teclado",
    "microfono_ocupado",
    "sin_microfono",
    "modelo_faltante",
    "ia_sin_respuesta",
    "ia_clave_invalida",
    "traduccion_fallo",
    "generico",
}
JERGA = ("evdev", "uinput", "d-bus", "dbus", "portal", "wayland", "api", "stderr", "traceback")


def _sin_comandos(texto: str) -> str:
    """Lo que va entre comillas invertidas es un comando copiable: ahí la jerga es inevitable."""
    return re.sub(r"`[^`]*`", "", texto)


def test_estan_todos_los_codigos_del_contrato() -> None:
    assert set(CODIGOS) == ESPERADOS


@pytest.mark.parametrize("codigo", sorted(ESPERADOS))
def test_cada_codigo_dice_que_paso_y_que_hacer(codigo: str) -> None:
    explicacion = explicar(codigo)

    assert isinstance(explicacion, Explicacion)
    assert explicacion.que_paso.strip() and explicacion.que_hacer.strip()


@pytest.mark.parametrize("codigo", sorted(ESPERADOS))
def test_las_frases_son_cortas_y_de_una_idea(codigo: str) -> None:
    explicacion = explicar(codigo)

    assert len(explicacion.que_paso) <= 120 and len(explicacion.que_hacer) <= 160


@pytest.mark.parametrize("codigo", sorted(ESPERADOS))
def test_no_hay_jerga_fuera_de_un_comando_copiable(codigo: str) -> None:
    explicacion = explicar(codigo)
    texto = _sin_comandos(f"{explicacion.que_paso} {explicacion.que_hacer}").lower()

    assert not [palabra for palabra in JERGA if re.search(rf"\b{re.escape(palabra)}\b", texto)]


@pytest.mark.parametrize("codigo", sorted(ESPERADOS))
def test_ninguna_frase_lleva_rutas_ni_claves(codigo: str) -> None:
    explicacion = explicar(codigo)
    texto = f"{explicacion.que_paso} {explicacion.que_hacer}"

    assert "/home" not in texto and "sk-" not in texto and "~/" not in texto


@pytest.mark.parametrize("codigo", ["", "no_existe", "PEGADO_FALLO", "  "])
def test_un_codigo_desconocido_da_el_generico_sin_fallar(codigo: str) -> None:
    assert explicar(codigo) == explicar(GENERICO)


def test_el_generico_remite_al_historial_y_al_diagnostico() -> None:
    explicacion = explicar("generico")

    assert "historial" in explicacion.que_hacer.lower()


def test_el_pegado_fallido_dice_que_el_texto_esta_a_salvo() -> None:
    assert "a salvo" in explicar("pegado_fallo").que_hacer.lower()


def test_la_traduccion_fallida_avisa_que_no_se_pego_nada() -> None:
    assert "no pegué nada" in explicar("traduccion_fallo").que_paso.lower()


def test_todo_esta_en_segunda_persona_rioplatense() -> None:
    hacer = " ".join(explicar(c).que_hacer for c in ESPERADOS).lower()

    assert any(forma in hacer for forma in ("tocá", "pegá", "conectá", "cerrala", "elegí"))
