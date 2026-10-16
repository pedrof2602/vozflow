import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.dominio.limpieza import LARGO_MAXIMO_DE_REPETICION, limpiar

# ---- muletillas que siempre se quitan --------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("eh necesito el archivo", "necesito el archivo"),
        ("necesito eh el archivo", "necesito el archivo"),
        ("mmm no sé", "no sé"),
        ("ehm, vamos", "vamos"),
        ("tengo um que ir", "tengo que ir"),
        ("uh I think so", "I think so"),
        ("EH, hola", "hola"),
        ("em, listo", "listo"),
    ],
)
def test_quita_las_muletillas_de_sonido(entrada: str, esperado: str) -> None:
    assert limpiar(entrada, None) == esperado


@pytest.mark.parametrize(
    "texto",
    ["el umbral es alto", "la empresa crece", "sin embargo, sigo", "ahora mismo", "un humano"],
)
def test_no_toca_palabras_que_contienen_una_muletilla(texto: str) -> None:
    assert limpiar(texto, None) == texto


# ---- muletillas que solo se quitan si están entre pausas ------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("este, necesito el archivo", "necesito el archivo"),
        ("o sea, necesito el archivo", "necesito el archivo"),
        ("bueno, vamos a empezar", "vamos a empezar"),
        ("primero, este, vamos a ver", "primero, vamos a ver"),
        ("necesito el archivo, o sea.", "necesito el archivo."),
        ("Ya terminé. Este, ahora sigo", "Ya terminé. ahora sigo"),
    ],
)
def test_quita_muletillas_de_palabra_solo_cuando_van_entre_pausas(
    entrada: str, esperado: str
) -> None:
    assert limpiar(entrada, "es") == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "este archivo es nuevo",
        "o sea que no vienes",
        "el bueno, el malo y el feo",
        "dame este, no ese",
        "ese es bueno",
    ],
)
def test_conserva_esas_palabras_cuando_son_parte_de_la_frase(texto: str) -> None:
    assert limpiar(texto, "es") == texto


def test_muletillas_en_ingles_entre_pausas() -> None:
    assert limpiar("so, you know, it works", "en") == "so, it works"
    assert limpiar("I mean, it works", "en") == "it works"


# ---- repeticiones inmediatas -----------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("tengo que, tengo que hacer el deploy", "tengo que hacer el deploy"),
        ("Tengo que tengo que hacer algo", "Tengo que hacer algo"),
        ("voy a ir voy a ir al banco", "voy a ir al banco"),
        ("el el perro", "el perro"),
        ("yo yo quiero", "yo quiero"),
        ("I I think so", "I think so"),
        ("the the test", "the test"),
        ("que, que pasó", "que pasó"),
    ],
)
def test_colapsa_repeticiones_inmediatas(entrada: str, esperado: str) -> None:
    assert limpiar(entrada, None) == esperado


@pytest.mark.parametrize(
    "texto",
    ["muy muy bueno", "no no no", "ja ja ja", "poco a poco", "bye bye", "dame dame"],
)
def test_conserva_repeticiones_de_una_palabra_con_sentido_propio(texto: str) -> None:
    assert limpiar(texto, None) == texto


# ---- sin cambios, espacios y saltos de línea -------------------------------


@pytest.mark.parametrize(
    "texto",
    ["Hola, ¿cómo estás? Todo bien.", "deploy del branch nuevo", "", "Sí."],
)
def test_no_cambia_un_texto_sin_muletillas(texto: str) -> None:
    assert limpiar(texto, None) == texto


def test_deja_espacios_simples_y_sin_bordes() -> None:
    assert limpiar("  hola   eh   mundo  ", None) == "hola mundo"


def test_conserva_los_saltos_de_linea_y_limpia_cada_linea() -> None:
    assert limpiar("eh primera línea\nsegunda  línea eh", None) == "primera línea\nsegunda línea"


def test_no_junta_repeticiones_a_traves_de_un_salto_de_linea() -> None:
    assert limpiar("el\nel perro", None) == "el\nel perro"


def test_no_deja_comas_sueltas_al_quitar_una_muletilla() -> None:
    assert limpiar("hola, eh, mundo", None) == "hola, mundo"
    assert limpiar("eh, eh, hola", None) == "hola"


# ---- propiedades -----------------------------------------------------------

_TEXTO = st.text(
    alphabet="abcdeéhmnoñsuyz ,.¿?¡!\n\t",
    max_size=80,
)
_PALABRAS_SEGURAS = ["casa", "perro", "código", "rápido", "mañana", "servidor", "archivo", "tren"]


@settings(max_examples=300)
@given(_TEXTO)
def test_limpiar_es_idempotente(texto: str) -> None:
    una_vez = limpiar(texto, None)
    assert limpiar(una_vez, None) == una_vez


@settings(max_examples=300)
@given(_TEXTO)
def test_el_resultado_no_tiene_espacios_dobles_ni_en_los_bordes_de_linea(texto: str) -> None:
    resultado = limpiar(texto, None)
    for linea in resultado.split("\n"):
        assert "  " not in linea
        assert linea == linea.strip()


@settings(max_examples=200)
@given(st.lists(st.sampled_from(_PALABRAS_SEGURAS), max_size=12))
def test_no_borra_palabras_que_no_son_muletillas(palabras: list[str]) -> None:
    # Sin muletillas y sin palabras vecinas iguales, el texto debe quedar idéntico.
    sin_repetidas = [p for i, p in enumerate(palabras) if i == 0 or p != palabras[i - 1]]
    texto = " ".join(sin_repetidas)
    # Evita frases repetidas (p. ej. "casa perro casa perro"), que sí se colapsan.
    for n in range(2, LARGO_MAXIMO_DE_REPETICION + 1):
        for i in range(len(sin_repetidas) - 2 * n + 1):
            if sin_repetidas[i : i + n] == sin_repetidas[i + n : i + 2 * n]:
                return
    assert limpiar(texto, None) == texto
