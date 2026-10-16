import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.dominio.puntuacion import normalizar_puntuacion

# ---- mayúsculas -------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("hola. cómo estás? bien! gracias", "Hola. ¿Cómo estás? ¡Bien! Gracias."),
        ("Hola, ¿cómo estás? Todo bien.", "Hola, ¿cómo estás? Todo bien."),
        ("ya terminé. 3 archivos listos", "Ya terminé. 3 archivos listos."),
        ("dijo: hola a todos", "Dijo: hola a todos."),
        ("bueno... no sé", "Bueno... no sé."),
        ("hola", "Hola"),
        ("él vino", "Él vino."),
        ("", ""),
    ],
)
def test_pone_mayuscula_al_inicio_y_tras_cada_oracion(entrada: str, esperado: str) -> None:
    assert normalizar_puntuacion(entrada, "es") == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("abrí main.py ahora", "Abrí main.py ahora."),
        ("uso node.js y npm", "Uso node.js y npm."),
        ("mira http://x.com/a ya", "Mira http://x.com/a ya."),
        ("corre git status", "Corre git status."),
        ("hola. main.py falla", "Hola. main.py falla."),
    ],
)
def test_no_capitaliza_ni_parte_nombres_de_archivo_ni_direcciones(
    entrada: str, esperado: str
) -> None:
    assert normalizar_puntuacion(entrada, "es") == esperado


# ---- espacios alrededor de los signos ---------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("hola , mundo .", "Hola, mundo."),
        ("hola,mundo", "Hola, mundo."),
        ("Hola.Mundo", "Hola. Mundo."),
        ("uno;dos", "Uno; dos."),
        ("pi es 3.14 y 1,5 ok", "Pi es 3.14 y 1,5 ok."),
        ("son las 10:30 ya", "Son las 10:30 ya."),
        ("hola   mundo", "Hola mundo."),
    ],
)
def test_arregla_espacios_alrededor_de_los_signos(entrada: str, esperado: str) -> None:
    assert normalizar_puntuacion(entrada, "es") == esperado


# ---- signos invertidos ------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("cómo estás?", "¿Cómo estás?"),
        ("hola, cómo estás?", "Hola, ¿cómo estás?"),
        ("increíble!", "¡Increíble!"),
        ("sí! no? tal vez", "¡Sí! ¿No? Tal vez."),
        ("¿cómo estás?", "¿Cómo estás?"),
        ("si no vienes, qué hago?", "Si no vienes, ¿qué hago?"),
    ],
)
def test_agrega_signos_invertidos_en_espanol(entrada: str, esperado: str) -> None:
    assert normalizar_puntuacion(entrada, "es") == esperado


@pytest.mark.parametrize("idioma", ["en", None, "fr"])
def test_no_agrega_signos_invertidos_fuera_del_espanol(idioma: str | None) -> None:
    assert normalizar_puntuacion("how are you?", idioma) == "How are you?"


def test_el_espanol_con_region_tambien_cuenta() -> None:
    assert normalizar_puntuacion("cómo andás?", "es-AR") == "¿Cómo andás?"


# ---- punto final y saltos de línea ------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (
            "tengo que hacer el deploy del branch nuevo",
            "Tengo que hacer el deploy del branch nuevo.",
        ),
        ("hola", "Hola"),
        ("Tengo que ir, ", "Tengo que ir,"),
        ("¿Vienes?", "¿Vienes?"),
        ("listo.", "Listo."),
    ],
)
def test_agrega_punto_final_solo_a_frases_de_dos_o_mas_palabras(
    entrada: str, esperado: str
) -> None:
    assert normalizar_puntuacion(entrada, "es") == esperado


def test_no_agrega_punto_final_a_una_ruta_o_una_direccion() -> None:
    assert normalizar_puntuacion("abrir src/vozflow/main", "es") == "Abrir src/vozflow/main"
    assert normalizar_puntuacion("entra a http://x.com", "es") == "Entra a http://x.com"


def test_con_saltos_de_linea_el_punto_final_va_solo_en_la_ultima_linea() -> None:
    entrada = "primera línea\nsegunda línea"

    assert normalizar_puntuacion(entrada, "es") == "Primera línea\nSegunda línea."


# ---- propiedades -------------------------------------------------------------

_TEXTO = st.text(alphabet="abcdeéhimnoñsuyzl0123456789 ,.;:¿?¡!\n\t", max_size=80)


@settings(max_examples=400)
@given(_TEXTO, st.sampled_from(["es", "en", None]))
def test_es_idempotente(texto: str, idioma: str | None) -> None:
    una_vez = normalizar_puntuacion(texto, idioma)
    assert normalizar_puntuacion(una_vez, idioma) == una_vez


@settings(max_examples=400)
@given(_TEXTO, st.sampled_from(["es", "en", None]))
def test_nunca_deja_espacio_antes_de_un_signo_de_cierre(texto: str, idioma: str | None) -> None:
    resultado = normalizar_puntuacion(texto, idioma)

    assert not re.search(r"[ \t][,.;:?!]", resultado)


@pytest.mark.parametrize("texto", [",?", ",!", ", ?", "¿,?", "a,?", "!?", ",0?", "1,5?"])
def test_regresion_oraciones_degeneradas_no_rompen_la_idempotencia(texto: str) -> None:
    # El estrés encontró que «,?» daba «,¿?» y luego «, ¿?».
    una_vez = normalizar_puntuacion(texto, "es")

    assert normalizar_puntuacion(una_vez, "es") == una_vez


@pytest.mark.parametrize("texto", [",?", ",!", ", ?", "!?"])
def test_no_agrega_signo_invertido_a_una_oracion_sin_contenido(texto: str) -> None:
    assert "¿" not in normalizar_puntuacion(texto, "es")
    assert "¡" not in normalizar_puntuacion(texto, "es")


def test_una_coma_decimal_no_cuenta_como_pausa_para_el_signo_invertido() -> None:
    assert normalizar_puntuacion("cuánto es 1,5 más 2?", "es") == "¿Cuánto es 1,5 más 2?"
