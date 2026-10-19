"""¿La tecla elegida existe en el teclado de la persona? (002, RP-009)"""

from typing import Any

from evdev import ecodes

from vozflow.atajos.disponibilidad import atajo_disponible, proponer_tecla, teclas_del_teclado

COMPLETO = {
    ecodes.KEY_A, ecodes.KEY_SPACE, ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT, ecodes.KEY_F9, ecodes.KEY_F10, ecodes.KEY_D,
}  # fmt: skip
COMPACTO = COMPLETO - {ecodes.KEY_RIGHTCTRL}


def test_un_modificador_con_lado_existe_si_el_teclado_lo_tiene() -> None:
    assert atajo_disponible("RightCtrl", COMPLETO) is True
    assert atajo_disponible("RightCtrl", COMPACTO) is False


def test_una_tecla_de_funcion_existe_si_el_teclado_la_tiene() -> None:
    assert atajo_disponible("F9", COMPLETO) is True
    assert atajo_disponible("F12", COMPLETO) is False


def test_una_combinacion_necesita_la_tecla_principal_y_un_modificador_de_cada_grupo() -> None:
    assert atajo_disponible("Ctrl+Alt+D", COMPLETO) is True
    assert atajo_disponible("Ctrl+Alt+D", COMPLETO - {ecodes.KEY_D}) is False
    assert (
        atajo_disponible("Ctrl+Alt+D", COMPLETO - {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT})
        is False
    )


def test_con_cualquiera_de_los_dos_lados_del_modificador_alcanza() -> None:
    sin_izquierdo = COMPLETO - {ecodes.KEY_LEFTCTRL}

    assert atajo_disponible("Ctrl+D", sin_izquierdo) is True


def test_un_atajo_que_no_se_entiende_no_esta_disponible() -> None:
    assert atajo_disponible("TeclaQueNoExiste", COMPLETO) is False
    assert atajo_disponible("", COMPLETO) is False


def test_si_no_se_conocen_las_teclas_no_se_bloquea_a_nadie() -> None:
    assert atajo_disponible("RightCtrl", set()) is True


# ---- proponer otra ----------------------------------------------------------------------------------------


def test_propone_la_primera_tecla_cómoda_que_el_teclado_tenga() -> None:
    assert proponer_tecla(COMPACTO) == "RightAlt"
    assert proponer_tecla(COMPLETO) == "RightCtrl"


def test_no_propone_una_tecla_excluida() -> None:
    assert proponer_tecla(COMPACTO, excluir=["RightAlt"]) == "F9"


def test_se_compara_la_tecla_excluida_sin_importar_como_se_escriba() -> None:
    assert proponer_tecla(COMPACTO, excluir=["<Alt>"]) in ("RightAlt", "F9")
    assert proponer_tecla(COMPACTO, excluir=["rightalt"]) == "F9"


def test_si_no_hay_ninguna_candidata_devuelve_nada() -> None:
    assert proponer_tecla({ecodes.KEY_A}) is None


# ---- leer el teclado real -----------------------------------------------------------------------------------


class TecladoFalso:
    ruta = "/dev/input/event0"
    nombre = "Teclado de prueba"
    fd = 0

    def __init__(self, teclas: set[int]) -> None:
        self._teclas = teclas

    def teclas(self) -> set[int]:
        return self._teclas

    def leer(self) -> list[object]:
        return []

    def cerrar(self) -> None:
        pass


def test_junta_las_teclas_de_los_teclados_reales() -> None:
    uno = TecladoFalso(COMPACTO)
    otro = TecladoFalso({ecodes.KEY_A, ecodes.KEY_SPACE, ecodes.KEY_RIGHTCTRL})

    assert teclas_del_teclado(lambda: [uno, otro]) == COMPACTO | {ecodes.KEY_RIGHTCTRL}


def test_ignora_los_dispositivos_que_no_son_teclados() -> None:
    raton = TecladoFalso({ecodes.BTN_LEFT})
    raton.nombre = "Ratón"

    assert teclas_del_teclado(lambda: [raton]) == set()


def test_si_no_se_puede_leer_el_teclado_devuelve_vacio_sin_caerse() -> None:
    def falla() -> list[Any]:
        raise PermissionError("sin permiso")

    assert teclas_del_teclado(falla) == set()


def test_sin_conocer_las_teclas_propone_la_primera_que_no_este_ocupada() -> None:
    assert proponer_tecla(set()) == "RightCtrl"
    assert proponer_tecla(set(), excluir=["RightCtrl"]) == "RightAlt"
