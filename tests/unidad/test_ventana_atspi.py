"""La ventana activa por AT-SPI: una ayuda opcional que nunca debe estorbar."""

import json
import subprocess
from pathlib import Path

import pytest

from vozflow.ventana.atspi import VentanaActivaAtspi
from vozflow.ventana.puerto import InfoVentana


def _con_salida(salida: str):  # type: ignore[no-untyped-def]
    llamadas: list[tuple[list[str], float]] = []

    def ejecutar(comando: list[str], timeout_s: float) -> str:
        llamadas.append((comando, timeout_s))
        return salida

    ejecutar.llamadas = llamadas  # type: ignore[attr-defined]
    return ejecutar


def _falla_con(error: Exception):  # type: ignore[no-untyped-def]
    def ejecutar(comando: list[str], timeout_s: float) -> str:
        raise error

    return ejecutar


# ---- interpretar la respuesta del ayudante ---------------------------------------------------------


def test_interpreta_la_ventana_activa() -> None:
    salida = json.dumps({"aplicacion": "ptyxis", "titulo": "claude", "pid": 62896})

    ventana = VentanaActivaAtspi(ejecutar=_con_salida(salida)).consultar()

    assert ventana == InfoVentana(aplicacion="ptyxis", titulo="claude", pid=62896)


def test_sin_ventana_activa_devuelve_none() -> None:
    assert VentanaActivaAtspi(ejecutar=_con_salida("null\n")).consultar() is None


@pytest.mark.parametrize(
    "salida",
    [
        "",
        "no es json",
        "[]",
        '"texto"',
        '{"aplicacion": "x"}',
        '{"aplicacion": 5, "titulo": "", "pid": 1}',
    ],
)
def test_una_respuesta_rara_se_trata_como_sin_ventana(salida: str) -> None:
    assert VentanaActivaAtspi(ejecutar=_con_salida(salida)).consultar() is None


def test_el_nombre_de_la_aplicacion_viene_en_minusculas_y_sin_espacios_sobrantes() -> None:
    salida = json.dumps({"aplicacion": "  Google Chrome ", "titulo": "t", "pid": 1})

    ventana = VentanaActivaAtspi(ejecutar=_con_salida(salida)).consultar()

    assert ventana is not None and ventana.aplicacion == "google chrome"


# ---- nunca estorba ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired(cmd="x", timeout=1),
        subprocess.CalledProcessError(1, "x", stderr="boom"),
        FileNotFoundError("/usr/bin/python3"),
        OSError("sin permiso"),
    ],
)
def test_si_el_ayudante_falla_o_tarda_demasiado_devuelve_none(error: Exception) -> None:
    assert VentanaActivaAtspi(ejecutar=_falla_con(error)).consultar() is None


# ---- cómo se lanza el ayudante ----------------------------------------------------------------------------


def test_lanza_el_ayudante_con_el_python_del_sistema_aislado_y_un_tiempo_maximo() -> None:
    ejecutar = _con_salida("null")

    VentanaActivaAtspi(ejecutar=ejecutar).consultar()

    comando, timeout_s = ejecutar.llamadas[0]
    assert comando[:2] == ["/usr/bin/python3", "-I"]
    assert Path(comando[2]).name == "ayudante_atspi.py" and Path(comando[2]).is_file()
    assert timeout_s == 0.5


def test_se_puede_cambiar_el_tiempo_maximo() -> None:
    ejecutar = _con_salida("null")

    VentanaActivaAtspi(ejecutar=ejecutar, timeout_s=0.3).consultar()

    assert ejecutar.llamadas[0][1] == 0.3


# ---- privacidad ----------------------------------------------------------------------------------------------


def test_el_titulo_no_aparece_en_el_repr_ni_en_los_registros(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ventana = InfoVentana(aplicacion="chrome", titulo="Banco - saldo $1.000", pid=7)

    with caplog.at_level("DEBUG"):
        VentanaActivaAtspi(
            ejecutar=_con_salida(json.dumps({"aplicacion": "a", "titulo": "secreto", "pid": 1}))
        ).consultar()

    assert "Banco" not in repr(ventana) and "saldo" not in repr(ventana)
    assert "secreto" not in caplog.text


# ---- con el sistema de verdad ---------------------------------------------------------------------------------


def test_con_el_escritorio_real_responde_a_tiempo_o_dice_que_no_hay_nada() -> None:
    ventana = VentanaActivaAtspi().consultar()

    assert ventana is None or (isinstance(ventana.aplicacion, str) and ventana.pid > 0)
