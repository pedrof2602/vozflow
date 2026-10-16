import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.dominio.comandos_voz import ResultadoComandos, aplicar_comandos


def _es(texto: str, salto: str = "conservar") -> ResultadoComandos:
    return aplicar_comandos(texto, "es", salto)  # type: ignore[arg-type]


def _en(texto: str, salto: str = "conservar") -> ResultadoComandos:
    return aplicar_comandos(texto, "en", salto)  # type: ignore[arg-type]


# ---- los casos mínimos de contracts/comandos-de-voz.md ---------------------
# La mayúscula inicial («Hola») la agrega después el paso de puntuación.


def test_caso_minimo_coma_e_interrogacion() -> None:
    assert _es("hola coma cómo estás signo de interrogación").texto == "hola, ¿cómo estás?"


def test_caso_minimo_nueva_linea() -> None:
    assert _es("primera línea nueva línea segunda línea").texto == "primera línea\nsegunda línea"


def test_caso_minimo_palabra_que_no_es_comando() -> None:
    assert _es("el punto de control").texto == "el punto de control"


def test_caso_minimo_borra_eso_descarta_todo() -> None:
    resultado = _es("escribe esto borra eso")

    assert resultado.descartar is True
    assert resultado.texto == ""


def test_caso_minimo_ingles() -> None:
    assert _en("please open it period").texto == "please open it."


# ---- cada comando de la tabla ----------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("hola punto", "hola."),
        ("hola punto y aparte adiós", "hola.\n\nadiós"),
        ("uno coma dos", "uno, dos"),
        ("nota dos puntos revisar", "nota: revisar"),
        ("uno punto y coma dos", "uno; dos"),
        ("qué hora es interrogación", "¿qué hora es?"),
        ("qué hora es signo de interrogación", "¿qué hora es?"),
        ("increíble signo de exclamación", "¡increíble!"),
        ("increíble exclamación", "¡increíble!"),
        ("mira abre paréntesis esto cierra paréntesis ahora", "mira (esto) ahora"),
        ("dijo abre comillas hola cierra comillas y se fue", 'dijo "hola" y se fue'),
        ("primera frase punto segunda frase", "primera frase. segunda frase"),
    ],
)
def test_comandos_en_espanol(entrada: str, esperado: str) -> None:
    assert _es(entrada).texto == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("done period", "done."),
        ("done full stop", "done."),
        ("one comma two", "one, two"),
        ("note colon check", "note: check"),
        ("one semicolon two", "one; two"),
        ("really question mark", "really?"),
        ("wow exclamation mark", "wow!"),
        ("first new line second", "first\nsecond"),
        ("first new paragraph second", "first.\n\nsecond"),
        ("see open paren this close paren now", "see (this) now"),
        ("said open quote hi close quote and left", 'said "hi" and left'),
    ],
)
def test_comandos_en_ingles(entrada: str, esperado: str) -> None:
    assert _en(entrada).texto == esperado


def test_el_signo_invertido_va_despues_de_la_ultima_coma_de_la_oracion() -> None:
    assert _es("hola Pedro coma cómo andás interrogación").texto == "hola Pedro, ¿cómo andás?"


def test_el_signo_invertido_empieza_en_la_oracion_actual() -> None:
    texto = _es("ya terminé punto cómo te fue interrogación").texto

    assert texto == "ya terminé. ¿cómo te fue?"


def test_en_ingles_no_se_agregan_signos_invertidos() -> None:
    assert "¿" not in _en("how are you question mark").texto


def test_borra_la_ultima_frase_quita_solo_la_oracion_en_curso() -> None:
    assert _es("hola punto esto sobra borra la última frase").texto == "hola."
    assert _en("hello period this goes delete last sentence").texto == "hello."


def test_borra_la_ultima_frase_sin_oraciones_previas_deja_vacio() -> None:
    assert _es("esto sobra borra la última frase").texto == ""


# ---- coincidencia: mayúsculas, acentos y puntuación del motor --------------


@pytest.mark.parametrize(
    "entrada",
    ["primera NUEVA LINEA segunda", "primera Nueva Línea segunda", "primera nueva línea. segunda"],
)
def test_ignora_mayusculas_acentos_y_puntuacion_del_motor(entrada: str) -> None:
    resultado = _es(entrada).texto

    assert resultado.split("\n") == ["primera", "segunda"]


def test_la_puntuacion_del_motor_junto_al_comando_no_se_duplica() -> None:
    assert _es("hola, coma, qué tal").texto == "hola, qué tal"


# ---- cuándo una palabra NO es un comando -----------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "el punto de control",
        "las tres en punto",
        "un punto y coma",
        "tiene una coma mal puesta",
        "la nueva línea de código",
        "ese signo de interrogación es raro",
        "puntos de venta",
        "comas y puntos",
        "interrogaciones",
    ],
)
def test_no_interpreta_comandos_dentro_de_una_frase_normal(texto: str) -> None:
    assert _es(texto).texto == texto


@pytest.mark.parametrize(
    "texto",
    ["the period of time", "a full stop sign", "in the new line", "my comma splice"],
)
def test_no_interpreta_comandos_ingleses_dentro_de_una_frase_normal(texto: str) -> None:
    assert _en(texto).texto == texto


def test_un_comando_de_otro_idioma_no_se_interpreta() -> None:
    assert _es("it works period").texto == "it works period"
    assert _en("funciona punto").texto == "funciona punto"


def test_sin_idioma_se_aceptan_los_dos() -> None:
    assert aplicar_comandos("listo punto", None, "conservar").texto == "listo."
    assert aplicar_comandos("done period", None, "conservar").texto == "done."


def test_acepta_el_idioma_con_region() -> None:
    assert aplicar_comandos("listo punto", "es-AR", "conservar").texto == "listo."


# ---- el modo «espacio» nunca emite saltos de línea ------------------------


def test_modo_espacio_convierte_nueva_linea_en_espacio() -> None:
    assert _es("uno nueva línea dos", "espacio").texto == "uno dos"


def test_modo_espacio_convierte_punto_y_aparte_en_punto_y_espacio() -> None:
    assert _es("uno punto y aparte dos", "espacio").texto == "uno. dos"


_PIEZAS = [
    "hola",
    "mundo",
    "nueva línea",
    "punto y aparte",
    "punto",
    "coma",
    "new line",
    "new paragraph",
    "abre paréntesis",
    "cierra paréntesis",
    "dos puntos",
]


@settings(max_examples=300)
@given(st.lists(st.sampled_from(_PIEZAS), max_size=10))
def test_el_modo_espacio_nunca_produce_un_salto_de_linea(piezas: list[str]) -> None:
    texto = " ".join(piezas)

    resultado = aplicar_comandos(texto, None, "espacio")

    assert "\n" not in resultado.texto


@settings(max_examples=200)
@given(st.lists(st.sampled_from(["hola", "mundo", "código", "servidor", "tren"]), max_size=10))
def test_un_texto_sin_comandos_queda_igual(palabras: list[str]) -> None:
    texto = " ".join(palabras)

    resultado = aplicar_comandos(texto, None, "conservar")

    assert resultado == ResultadoComandos(texto=texto, descartar=False)


# ---- regresiones ------------------------------------------------------------


def test_regresion_el_verbo_estas_con_tilde_no_es_el_determinante_estas() -> None:
    # Al comparar sin acentos, «estás» (verbo) se confundía con «estas» (determinante).
    assert _es("cómo estás punto").texto == "cómo estás."
    assert _es("compré estas punto").texto == "compré estas punto"


def test_regresion_cerrar_y_abrir_funcionan_tras_un_determinante() -> None:
    assert _en("see open paren this close paren now").texto == "see (this) now"
    assert _es("dame abre comillas este cierra comillas").texto == 'dame "este"'
