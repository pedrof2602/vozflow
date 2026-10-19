"""Los textos de los ajustes: llanos, cortos y con ayuda en cada opción (002, RP-017)."""

import re

import pytest

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.textos import TEXTOS, Texto, ayuda_de, texto_de

JERGA = (
    "evdev", "uinput", "d-bus", "dbus", "portal", "wayland", "api", "llm", "cpu", "gpu",
    "hilos", "whisper", "token", "stderr", "regex", "json", "sqlite", "faster",
)  # fmt: skip
SIGLAS_PERMITIDAS = {"IA"}  # «IA» siempre va acompañada de «asistente»


def test_toda_clave_de_ajuste_tiene_su_texto() -> None:
    claves = set(AjustesRepo(abrir_base(":memory:")).todos())

    # «asistente.hecho» no es una opción: la persona ve «asistente.repetir».
    faltan = [c for c in claves if c not in TEXTOS and c != "asistente.hecho"]
    assert faltan == []


def test_las_opciones_que_no_son_ajustes_tambien_tienen_texto() -> None:
    for clave in ("autoinicio", "asistente.repetir", "copia.exportar", "copia.importar"):
        assert clave in TEXTOS


@pytest.mark.parametrize("clave", sorted(TEXTOS))
def test_cada_opcion_tiene_titulo_y_ayuda_de_una_linea(clave: str) -> None:
    texto = TEXTOS[clave]

    assert isinstance(texto, Texto)
    assert texto.titulo.strip() and texto.ayuda.strip()
    assert "\n" not in texto.titulo and "\n" not in texto.ayuda
    assert len(texto.titulo) <= 45 and len(texto.ayuda) <= 150


@pytest.mark.parametrize("clave", sorted(TEXTOS))
def test_no_hay_jerga(clave: str) -> None:
    texto = f"{TEXTOS[clave].titulo} {TEXTOS[clave].ayuda}".lower()

    assert not [j for j in JERGA if re.search(rf"\b{re.escape(j)}\b", texto)]


@pytest.mark.parametrize("clave", sorted(TEXTOS))
def test_no_hay_siglas_sin_explicar(clave: str) -> None:
    texto = f"{TEXTOS[clave].titulo} {TEXTOS[clave].ayuda}"

    siglas = set(re.findall(r"\b[A-ZÁÉÍÓÚÑ]{2,}\b", texto)) - SIGLAS_PERMITIDAS
    assert siglas == set()


@pytest.mark.parametrize("clave", sorted(TEXTOS))
def test_esta_escrito_en_segunda_persona_y_sin_punto_final_en_el_titulo(clave: str) -> None:
    assert not TEXTOS[clave].titulo.endswith(".")


def test_la_ayuda_de_la_tecla_para_dictar_explica_como_se_usa() -> None:
    assert "apretada" in ayuda_de("atajo.mantener").lower()


def test_texto_de_una_clave_desconocida_es_un_error_claro() -> None:
    with pytest.raises(KeyError, match="texto"):
        texto_de("no.existe")


def test_ayuda_de_devuelve_la_frase() -> None:
    assert ayuda_de("interfaz.tema") == TEXTOS["interfaz.tema"].ayuda
