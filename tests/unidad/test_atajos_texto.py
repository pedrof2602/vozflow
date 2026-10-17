"""Expansión de atajos de texto (RF-020): palabra completa, el más largo gana, sin acentos."""

from hypothesis import given
from hypothesis import strategies as st

from vozflow.dominio.atajos_texto import AtajoTexto, expandir

FIRMA = AtajoTexto("mi firma", "Pedro Freimeyer\nSaludos")
ASK = AtajoTexto("ask", "pedido")


def test_expande_una_frase_completa() -> None:
    assert expandir("hola, mi firma", [FIRMA]) == "hola, Pedro Freimeyer\nSaludos"


def test_expande_una_palabra_sola() -> None:
    assert expandir("el ask es claro", [ASK]) == "el pedido es claro"


def test_no_actua_dentro_de_otra_palabra() -> None:
    assert expandir("tasks y pregunta y asking", [ASK]) == "tasks y pregunta y asking"


def test_no_actua_con_letras_numeros_o_guion_bajo_pegados() -> None:
    assert expandir("xask y ask1 y _ask", [ASK]) == "xask y ask1 y _ask"


def test_si_dos_coinciden_gana_el_disparador_mas_largo() -> None:
    atajos = [ASK, AtajoTexto("investor ask", "pedido al inversor")]

    assert expandir("el investor ask", atajos) == "el pedido al inversor"
    assert expandir("investor ask y ask", atajos) == "pedido al inversor y pedido"


def test_el_orden_de_la_lista_no_cambia_el_resultado() -> None:
    a = [ASK, AtajoTexto("investor ask", "largo")]

    assert expandir("investor ask", a) == expandir("investor ask", a[::-1])


def test_no_distingue_mayusculas() -> None:
    assert expandir("Mi Firma y MI FIRMA", [AtajoTexto("mi firma", "X")]) == "X y X"


def test_no_distingue_acentos() -> None:
    atajo = AtajoTexto("mi dirección", "Calle 1")

    assert expandir("mi direccion y mi DIRECCIÓN", [atajo]) == "Calle 1 y Calle 1"


def test_el_acento_del_texto_original_se_conserva_fuera_de_los_atajos() -> None:
    assert expandir("canción y ask", [ASK]) == "canción y pedido"


def test_tolera_espacios_y_saltos_entre_las_palabras_del_disparador() -> None:
    assert expandir("mi   firma y mi\nfirma", [FIRMA]).count("Pedro") == 2


def test_la_puntuacion_vecina_no_impide_la_expansion() -> None:
    assert expandir("¿mi firma? (ask), ask.", [FIRMA, ASK]).startswith("¿Pedro")
    assert "(pedido)" in expandir("(ask)", [ASK])


def test_el_reemplazo_se_inserta_tal_cual_sin_interpretar_barras() -> None:
    atajo = AtajoTexto("ruta", r"C:\nueva\1 \g<0>")

    assert expandir("ruta", [atajo]) == r"C:\nueva\1 \g<0>"


def test_un_reemplazo_que_contiene_otro_disparador_no_se_expande_otra_vez() -> None:
    atajos = [AtajoTexto("a", "b"), AtajoTexto("b", "c")]

    assert expandir("a", atajos) == "b"


def test_el_punto_final_que_puso_la_puntuacion_no_queda_pegado_al_reemplazo() -> None:
    assert expandir("Mi firma.", [FIRMA]) == "Pedro Freimeyer\nSaludos"


def test_un_punto_en_medio_del_texto_se_conserva() -> None:
    assert expandir("Mira el ask. Gracias.", [ASK]) == "Mira el pedido. Gracias."


def test_sin_atajos_o_sin_texto_no_hace_nada() -> None:
    assert expandir("hola", []) == "hola"
    assert expandir("", [ASK]) == ""


def test_varias_apariciones() -> None:
    assert expandir("ask ask ask", [ASK]) == "pedido pedido pedido"


_PALABRAS_DE_TEXTO = st.sampled_from(["hola", "casa", "tasks", "pregunta", "uno", "dos", "pedido"])
_PALABRAS_DE_DISPARADOR = st.sampled_from(["xx", "yy", "zz", "xx yy", "zz xx"])


@given(
    st.lists(_PALABRAS_DE_TEXTO, max_size=12),
    st.lists(_PALABRAS_DE_DISPARADOR, min_size=1, max_size=5),
    st.sampled_from([" ", "  ", "\n", ", ", ". "]),
)
def test_nunca_modifica_un_texto_que_no_contiene_ningun_disparador(
    palabras: list[str], disparadores: list[str], separador: str
) -> None:
    texto = separador.join(palabras)
    atajos = [AtajoTexto(d, "REEMPLAZO") for d in disparadores]

    assert expandir(texto, atajos) == texto
