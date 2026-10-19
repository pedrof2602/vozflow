"""La barra de texto de ``descargar-modelo`` (002, RP-004): «██▌ 62 % · 300/480 MB»."""

import io

import pytest

from tests.dobles import MotorFalso
from tests.unidad.test_cli_dictar import GrabadoraFalsa, _dependencias
from vozflow.__main__ import CODIGO_ERROR, CODIGO_OK, main
from vozflow.barra import BarraDeTexto, barra_de_texto
from vozflow.transcripcion.motor import ErrorDeTranscripcion

MB = 1_000_000


def test_una_barra_vacia() -> None:
    assert barra_de_texto(0, 480 * MB, ancho=10) == "░░░░░░░░░░ 0 % · 0/480 MB"


def test_una_barra_a_medias() -> None:
    assert barra_de_texto(240 * MB, 480 * MB, ancho=10) == "█████░░░░░ 50 % · 240/480 MB"


def test_una_barra_completa() -> None:
    assert barra_de_texto(480 * MB, 480 * MB, ancho=10) == "██████████ 100 % · 480/480 MB"


def test_lo_que_se_pasa_del_total_se_corta_en_100() -> None:
    assert barra_de_texto(500 * MB, 480 * MB, ancho=10).startswith("██████████ 100 %")


def test_sin_total_conocido_no_se_inventa_un_porcentaje() -> None:
    assert barra_de_texto(10 * MB, 0) == "Descargando… 10 MB"


def test_el_ancho_por_defecto_es_de_veinte_casillas() -> None:
    assert len(barra_de_texto(0, MB).split(" ")[0]) == 20


# ---- escribir la barra ---------------------------------------------------------------------------------------


class Terminal(io.StringIO):
    def __init__(self, es_terminal: bool) -> None:
        super().__init__()
        self._es = es_terminal

    def isatty(self) -> bool:
        return self._es


def test_en_una_terminal_la_barra_se_redibuja_en_la_misma_linea() -> None:
    salida = Terminal(True)
    barra = BarraDeTexto(salida, ancho=10)

    barra(100 * MB, 480 * MB)
    barra(480 * MB, 480 * MB)
    barra.terminar()

    texto = salida.getvalue()
    assert texto.count("\r") == 2 and texto.endswith("\n")
    assert "100 %" in texto


def test_sin_terminal_solo_escribe_cada_diez_por_ciento() -> None:
    salida = Terminal(False)
    barra = BarraDeTexto(salida, ancho=10)

    for hechos in range(0, 481, 4):  # muchos avances chicos
        barra(hechos * MB, 480 * MB)
    barra.terminar()

    lineas = salida.getvalue().splitlines()
    assert 5 <= len(lineas) <= 12 and "\r" not in salida.getvalue()
    assert lineas[-1].startswith("██████████ 100 %")


def test_terminar_sin_avances_no_escribe_nada() -> None:
    salida = Terminal(True)

    BarraDeTexto(salida).terminar()

    assert salida.getvalue() == ""


# ---- el comando -----------------------------------------------------------------------------------------------


def test_descargar_modelo_muestra_la_barra_y_el_destino(
    capsys: pytest.CaptureFixture[str],
) -> None:
    dependencias = _dependencias(GrabadoraFalsa(), MotorFalso())

    def con_avance(modelo: str, al_avance) -> str:  # type: ignore[no-untyped-def]
        al_avance(0, 480 * MB)
        al_avance(480 * MB, 480 * MB)
        return f"/modelos/{modelo}"

    dependencias.descargar_modelo_con_avance = con_avance

    codigo = main(["descargar-modelo"], dependencias)

    salida = capsys.readouterr()
    assert codigo == CODIGO_OK
    assert "100 %" in salida.err and "480/480 MB" in salida.err
    assert "/modelos/small" in salida.out


def test_si_la_descarga_con_barra_falla_lo_dice_en_palabras_llanas(
    capsys: pytest.CaptureFixture[str],
) -> None:
    dependencias = _dependencias(GrabadoraFalsa(), MotorFalso())

    def sin_red(modelo: str, al_avance) -> str:  # type: ignore[no-untyped-def]
        raise ErrorDeTranscripcion("detalle técnico", "modelo_faltante")

    dependencias.descargar_modelo_con_avance = sin_red

    codigo = main(["descargar-modelo"], dependencias)

    err = capsys.readouterr().err
    assert codigo == CODIGO_ERROR
    assert "Falta el modelo de voz" in err and "internet" in err
