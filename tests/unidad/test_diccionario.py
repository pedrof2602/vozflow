"""La pista para el motor a partir del diccionario (RF-019)."""

from hypothesis import given
from hypothesis import strategies as st

from vozflow.dominio.diccionario import TOPE_POR_DEFECTO, construir_pista


def test_sin_palabras_no_hay_pista() -> None:
    assert construir_pista([], 100) is None


def test_une_las_palabras_con_comas() -> None:
    assert construir_pista(["SQLAlchemy", "FastAPI"], 100) == "SQLAlchemy, FastAPI"


def test_una_sola_palabra() -> None:
    assert construir_pista(["Kubernetes"], 100) == "Kubernetes"


def test_si_no_caben_todas_entran_primero_las_mas_recientes() -> None:
    palabras = ["vieja", "media", "nueva"]  # de la más vieja a la más nueva

    pista = construir_pista(palabras, len("media, nueva"))

    assert pista == "media, nueva"


def test_se_conserva_el_orden_de_alta_entre_las_que_entran() -> None:
    assert construir_pista(["a", "b", "c", "d"], 7) == "b, c, d"


def test_una_palabra_mas_larga_que_el_tope_se_salta_y_entran_las_demas() -> None:
    pista = construir_pista(["corta", "larguisima" * 5, "otra"], 12)

    assert pista == "corta, otra"


def test_si_ninguna_cabe_no_hay_pista() -> None:
    assert construir_pista(["abcdefghij"], 5) is None


def test_el_tope_cuenta_los_separadores() -> None:
    assert construir_pista(["abc", "def"], 8) == "abc, def"
    assert construir_pista(["abc", "def"], 7) == "def"


def test_ignora_palabras_vacias_y_repetidas() -> None:
    assert construir_pista(["uno", "", "UNO", "dos", "  "], 100) == "uno, dos"


def test_hay_un_tope_por_defecto_razonable() -> None:
    assert 100 <= TOPE_POR_DEFECTO <= 800


@given(
    st.lists(st.text(min_size=1, max_size=30), max_size=40), st.integers(min_value=1, max_value=200)
)
def test_nunca_pasa_el_tope(palabras: list[str], tope: int) -> None:
    pista = construir_pista(palabras, tope)

    assert pista is None or len(pista) <= tope
