"""El insertor completo con dobles: copiar, pegar con la cadena de respaldo y restaurar (RF-018)."""

from collections.abc import Sequence

import pytest

from vozflow.insercion import crear_insertor
from vozflow.insercion.insertor import InsertorPorTeclas
from vozflow.insercion.portal_remoto import TecladorPortal
from vozflow.insercion.portapapeles import PortapapelesNoLegible
from vozflow.insercion.puerto import AtajoDePegado, Destino, FalloDeTeclado
from vozflow.insercion.ydotool import TecladorYdotool

RETURN, KP_ENTER = 0xFF0D, 0xFF8D
SHIFT, INSERT, CTRL, V = 0xFFE1, 0xFF63, 0xFFE3, 0x76


class PortapapelesFalso:
    def __init__(self, contenido: str | None = "lo que Pedro tenía") -> None:
        self.contenido = contenido  # None = no se puede leer
        self.primaria = ""
        self.eventos: list[str] = []
        self.fallar_al_copiar = False

    def leer(self) -> str:
        self.eventos.append("leer")
        if self.contenido is None:
            raise PortapapelesNoLegible("no es texto")
        return self.contenido

    def copiar(self, texto: str, *, tambien_primaria: bool) -> None:
        self.eventos.append(f"copiar:{texto}:{tambien_primaria}")
        if self.fallar_al_copiar:
            raise OSError("wl-copy falló")
        self.contenido = texto
        if tambien_primaria:
            self.primaria = texto

    def limpiar(self) -> None:
        self.eventos.append("limpiar")
        self.contenido = ""


class TecladorFalso:
    def __init__(self, portapapeles: PortapapelesFalso, falla: bool = False) -> None:
        self.portapapeles = portapapeles
        self.falla = falla
        self.combinaciones: list[tuple[int, ...]] = []
        self.contenido_al_pegar: list[str | None] = []

    def pulsar_combinacion(self, teclas: Sequence[int]) -> None:
        self.combinaciones.append(tuple(teclas))
        self.contenido_al_pegar.append(self.portapapeles.contenido)
        if self.falla:
            raise FalloDeTeclado("el teclado falló")


def _montar(
    *, primero_falla: bool = False, segundo_falla: bool = False, contenido: str | None = "previo"
) -> tuple[InsertorPorTeclas, PortapapelesFalso, TecladorFalso, TecladorFalso, list[float]]:
    portapapeles = PortapapelesFalso(contenido)
    primero = TecladorFalso(portapapeles, primero_falla)
    segundo = TecladorFalso(portapapeles, segundo_falla)
    pausas: list[float] = []
    insertor = InsertorPorTeclas(portapapeles, [primero, segundo], dormir=pausas.append)
    return insertor, portapapeles, primero, segundo, pausas


# ---- el camino feliz ------------------------------------------------------------------------------


def test_copia_el_texto_pega_con_shift_insert_y_restaura_el_portapapeles() -> None:
    insertor, portapapeles, primero, _, _ = _montar()

    resultado = insertor.insertar("hola mundo", Destino())

    assert resultado.insertado is True
    assert primero.combinaciones == [(SHIFT, INSERT)]
    assert primero.contenido_al_pegar == ["hola mundo"]  # al pegar, el portapapeles tenía el texto
    assert portapapeles.contenido == "previo"  # y después volvió a como estaba


def test_copia_a_las_dos_selecciones_para_que_shift_insert_y_ctrl_v_vean_lo_mismo() -> None:
    insertor, portapapeles, *_ = _montar()

    insertor.insertar("hola", Destino())

    assert "copiar:hola:True" in portapapeles.eventos


def test_espera_a_que_la_aplicacion_lea_antes_de_restaurar() -> None:
    insertor, portapapeles, _, _, pausas = _montar()

    insertor.insertar("hola", Destino())

    assert pausas and pausas[0] > 0
    assert portapapeles.eventos.index("copiar:previo:False") > portapapeles.eventos.index(
        "copiar:hola:True"
    )


def test_usa_el_atajo_que_pide_el_destino() -> None:
    insertor, _, primero, _, _ = _montar()

    insertor.insertar("hola", Destino(atajo=AtajoDePegado.CTRL_SHIFT_V))

    assert primero.combinaciones == [(CTRL, SHIFT, V)]


def test_con_salto_espacio_pega_el_texto_sin_saltos() -> None:
    insertor, _, primero, _, _ = _montar()

    insertor.insertar("uno\ndos", Destino(salto_de_linea="espacio"))

    assert primero.contenido_al_pegar == ["uno dos"]


def test_un_texto_con_saltos_se_pega_entero_y_sin_mandar_enter() -> None:
    insertor, _, primero, _, _ = _montar()

    insertor.insertar("uno\ndos", Destino())

    assert primero.contenido_al_pegar == ["uno\ndos"]
    assert all(t not in (RETURN, KP_ENTER) for c in primero.combinaciones for t in c)


def test_un_texto_vacio_no_toca_nada() -> None:
    insertor, portapapeles, primero, _, _ = _montar()

    resultado = insertor.insertar("", Destino())

    assert resultado.insertado is True
    assert portapapeles.eventos == [] and primero.combinaciones == []


# ---- la cadena de respaldo ---------------------------------------------------------------------------


def test_si_el_primero_falla_pega_con_el_segundo_y_restaura() -> None:
    insertor, portapapeles, primero, segundo, _ = _montar(primero_falla=True)

    resultado = insertor.insertar("hola", Destino())

    assert resultado.insertado is True
    assert len(primero.combinaciones) == 1 and len(segundo.combinaciones) == 1
    assert portapapeles.contenido == "previo"


def test_si_fallan_todos_devuelve_fallido_sin_lanzar_y_restaura() -> None:
    insertor, portapapeles, *_ = _montar(primero_falla=True, segundo_falla=True)

    resultado = insertor.insertar("texto privado", Destino())

    assert resultado.insertado is False
    assert resultado.motivo
    assert portapapeles.contenido == "previo"


def test_el_motivo_del_fallo_no_incluye_el_texto_dictado() -> None:
    insertor, *_ = _montar(primero_falla=True, segundo_falla=True)

    resultado = insertor.insertar("texto privado", Destino())

    assert "texto privado" not in (resultado.motivo or "")


def test_sin_tecladores_es_un_fallo_claro() -> None:
    insertor = InsertorPorTeclas(PortapapelesFalso(), [], dormir=lambda _: None)

    resultado = insertor.insertar("hola", Destino())

    assert resultado.insertado is False


def test_si_no_se_puede_copiar_no_se_intenta_pegar() -> None:
    insertor, portapapeles, primero, *_ = _montar()
    portapapeles.fallar_al_copiar = True

    resultado = insertor.insertar("hola", Destino())

    assert resultado.insertado is False
    assert primero.combinaciones == []


# ---- el portapapeles de Pedro ------------------------------------------------------------------------------


def test_si_estaba_vacio_queda_vacio() -> None:
    insertor, portapapeles, *_ = _montar(contenido="")

    insertor.insertar("hola", Destino())

    assert portapapeles.contenido == ""
    assert "limpiar" in portapapeles.eventos


def test_si_no_se_pudo_leer_no_se_inventa_una_restauracion() -> None:
    insertor, portapapeles, *_ = _montar(contenido=None)

    resultado = insertor.insertar("hola", Destino())

    assert resultado.insertado is True
    assert not [e for e in portapapeles.eventos if e.startswith("copiar:") and "hola" not in e]
    assert "limpiar" not in portapapeles.eventos


def test_un_error_inesperado_del_teclador_tambien_restaura_y_no_lanza() -> None:
    portapapeles = PortapapelesFalso("previo")

    class Roto:
        def pulsar_combinacion(self, teclas: Sequence[int]) -> None:
            raise RuntimeError("algo imprevisto")

    insertor = InsertorPorTeclas(portapapeles, [Roto()], dormir=lambda _: None)

    resultado = insertor.insertar("hola", Destino())

    assert resultado.insertado is False
    assert portapapeles.contenido == "previo"


# ---- la configuración por defecto ----------------------------------------------------------------------------------


def test_crear_insertor_prueba_primero_ydotool_y_despues_el_portal() -> None:
    insertor = crear_insertor()

    assert isinstance(insertor, InsertorPorTeclas)
    assert [type(t) for t in insertor.tecladores] == [TecladorYdotool, TecladorPortal]


@pytest.mark.parametrize("texto", ["a", "ñandú ¿sí?", "línea\nsiguiente"])
def test_nunca_se_manda_enter_con_ningun_texto(texto: str) -> None:
    insertor, _, primero, segundo, _ = _montar()

    insertor.insertar(texto, Destino())

    for combinacion in (*primero.combinaciones, *segundo.combinaciones):
        assert RETURN not in combinacion and KP_ENTER not in combinacion


# ---- código del motivo para el historial (002, RP-021, RP-022) --------------------------------------------


def test_si_fallan_todos_los_tecladores_el_codigo_es_pegado_fallo() -> None:
    insertor, *_ = _montar(primero_falla=True, segundo_falla=True)

    assert insertor.insertar("hola", Destino()).codigo == "pegado_fallo"


def test_sin_tecladores_el_codigo_es_pegado_fallo() -> None:
    insertor = InsertorPorTeclas(PortapapelesFalso(), [], dormir=lambda _: None)

    assert insertor.insertar("hola", Destino()).codigo == "pegado_fallo"


def test_si_no_se_puede_copiar_el_codigo_es_sin_portapapeles() -> None:
    insertor, portapapeles, *_ = _montar()
    portapapeles.fallar_al_copiar = True

    assert insertor.insertar("hola", Destino()).codigo == "sin_portapapeles"


def test_un_pegado_exitoso_no_lleva_codigo() -> None:
    insertor, *_ = _montar()

    assert insertor.insertar("hola", Destino()).codigo == ""


def test_el_codigo_nunca_lleva_texto_libre() -> None:
    from vozflow.mensajes import CODIGOS

    insertor, *_ = _montar(primero_falla=True, segundo_falla=True)

    assert insertor.insertar("texto privado", Destino()).codigo in CODIGOS


def test_un_fallido_sin_codigo_explicito_usa_el_generico() -> None:
    from vozflow.insercion.puerto import ResultadoInsercion

    assert ResultadoInsercion.fallido("algo raro").codigo == "generico"
