import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.dominio.atajos_texto import AtajoTexto
from vozflow.dominio.tuberia import OpcionesDeTuberia, ResultadoProceso, procesar

TODO_ACTIVO = OpcionesDeTuberia()
NADA_ACTIVO = OpcionesDeTuberia(
    quitar_muletillas=False, puntuacion_automatica=False, comandos_de_voz=False
)


# ---- los ejemplos del plan y del contrato ----------------------------------


def test_ejemplo_de_la_historia_2() -> None:
    texto = "eh, o sea, tengo que, tengo que hacer el deploy del branch nuevo"

    resultado = procesar(texto, "es", TODO_ACTIVO)

    assert resultado == ResultadoProceso(texto="Tengo que hacer el deploy del branch nuevo.")


def test_ejemplo_de_comandos_del_contrato() -> None:
    texto = "hola coma cómo estás signo de interrogación"

    assert procesar(texto, "es", TODO_ACTIVO).texto == "Hola, ¿cómo estás?"


def test_ejemplo_en_ingles() -> None:
    assert procesar("please open it period", "en", TODO_ACTIVO).texto == "Please open it."


# ---- el orden importa: comandos → limpieza → puntuación --------------------


def test_los_comandos_van_antes_que_la_limpieza() -> None:
    # «coma» separa las dos mitades; solo después de convertirla en «,» la repetición
    # «tengo que, tengo que» es visible para la limpieza.
    resultado = procesar("tengo que coma tengo que hacer algo", "es", TODO_ACTIVO)

    assert resultado.texto == "Tengo que hacer algo."


def test_la_puntuacion_va_despues_de_la_limpieza() -> None:
    # Si la mayúscula se pusiera antes de quitar «eh», «mundo» quedaría en minúscula.
    resultado = procesar("eh, hola. eh, mundo", "es", TODO_ACTIVO)

    assert resultado.texto == "Hola. Mundo."


# ---- banderas de modo --------------------------------------------------------


def test_sin_comandos_de_voz_las_palabras_se_escriben_tal_cual() -> None:
    opciones = OpcionesDeTuberia(comandos_de_voz=False)

    assert procesar("hola coma mundo", "es", opciones).texto == "Hola coma mundo."


def test_sin_quitar_muletillas_se_conservan() -> None:
    opciones = OpcionesDeTuberia(quitar_muletillas=False)

    # Dos palabras: lleva punto final como cualquier frase.
    assert procesar("eh hola", "es", opciones).texto == "Eh hola."


def test_sin_puntuacion_automatica_no_se_agregan_mayusculas_ni_punto() -> None:
    opciones = OpcionesDeTuberia(puntuacion_automatica=False)

    assert procesar("hola mundo de nuevo", "es", opciones).texto == "hola mundo de nuevo"


def test_con_todo_apagado_el_texto_queda_exactamente_igual() -> None:
    texto = "  eh  hola coma   mundo ,\n borra eso  "

    assert procesar(texto, "es", NADA_ACTIVO) == ResultadoProceso(texto=texto)


# ---- descartar y saltos de línea --------------------------------------------


def test_borra_eso_descarta_el_dictado() -> None:
    resultado = procesar("escribe esto borra eso", "es", TODO_ACTIVO)

    assert resultado == ResultadoProceso(texto="", descartar=True)


def test_un_dictado_de_solo_muletillas_queda_vacio_sin_descartarse() -> None:
    resultado = procesar("eh, eh", "es", TODO_ACTIVO)

    assert resultado == ResultadoProceso(texto="", descartar=False)


def test_nueva_linea_conserva_el_salto() -> None:
    # La última línea tiene una sola palabra: sin punto final.
    assert procesar("uno nueva línea dos", "es", TODO_ACTIVO).texto == "Uno\nDos"


def test_en_modo_espacio_no_hay_saltos_de_linea() -> None:
    opciones = OpcionesDeTuberia(salto_de_linea="espacio")

    assert procesar("uno nueva línea dos", "es", opciones).texto == "Uno dos."


@pytest.mark.parametrize("comandos", [True, False])
def test_en_modo_espacio_los_saltos_que_ya_traia_el_texto_tambien_se_quitan(
    comandos: bool,
) -> None:
    opciones = OpcionesDeTuberia(comandos_de_voz=comandos, salto_de_linea="espacio")

    assert "\n" not in procesar("uno\ndos", "es", opciones).texto


_PIEZAS = [
    "hola",
    "eh",
    "mundo",
    "nueva línea",
    "punto y aparte",
    "coma",
    "que",
    "este",
    "borra eso",
]


@settings(max_examples=300)
@given(
    st.lists(st.sampled_from(_PIEZAS), max_size=10),
    st.booleans(),
    st.booleans(),
    st.booleans(),
)
def test_el_modo_espacio_nunca_produce_un_salto_con_ninguna_combinacion(
    piezas: list[str], muletillas: bool, puntuacion: bool, comandos: bool
) -> None:
    opciones = OpcionesDeTuberia(
        quitar_muletillas=muletillas,
        puntuacion_automatica=puntuacion,
        comandos_de_voz=comandos,
        salto_de_linea="espacio",
    )

    assert "\n" not in procesar(" ".join(piezas), None, opciones).texto


# ---- atajos de texto (RF-020) ----------------------------------------------


def test_expande_un_atajo_de_texto_al_final_de_la_tuberia() -> None:
    opciones = OpcionesDeTuberia(atajos=(AtajoTexto("mi firma", "Pedro\nFreimeyer"),))

    resultado = procesar("gracias por todo coma mi firma", "es", opciones)

    assert resultado.texto == "Gracias por todo, Pedro\nFreimeyer"


def test_el_reemplazo_no_pasa_por_la_limpieza_ni_la_puntuacion() -> None:
    opciones = OpcionesDeTuberia(atajos=(AtajoTexto("saludo", "eh, o sea, hola"),))

    assert procesar("saludo", "es", opciones).texto == "eh, o sea, hola"


def test_el_reemplazo_no_se_interpreta_como_comando_de_voz() -> None:
    opciones = OpcionesDeTuberia(atajos=(AtajoTexto("cierre", "borra eso"),))

    resultado = procesar("cierre", "es", opciones)

    assert resultado.descartar is False and resultado.texto == "borra eso"


def test_sin_atajos_el_texto_queda_igual_que_antes() -> None:
    assert procesar("hola mundo", "es", OpcionesDeTuberia()) == procesar(
        "hola mundo", "es", OpcionesDeTuberia(atajos=())
    )


def test_en_un_destino_de_una_sola_linea_el_reemplazo_tambien_se_aplana() -> None:
    opciones = OpcionesDeTuberia(
        atajos=(AtajoTexto("firma", "Saludos,\nPedro"),), salto_de_linea="espacio"
    )

    assert procesar("firma", "es", opciones).texto == "Saludos, Pedro"
