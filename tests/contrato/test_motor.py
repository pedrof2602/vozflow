"""Contrato de ``MotorDeTranscripcion`` (contracts/puertos.md).

La misma batería corre contra el doble y, con ``-m lento``, contra el motor real.
"""

import socket
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
import pytest

from tests.dobles import MotorFalso
from vozflow.audio.senal import FRECUENCIA
from vozflow.transcripcion.motor import (
    ErrorDeTranscripcion,
    MotorDeTranscripcion,
    Transcripcion,
)


def _motor_real() -> MotorDeTranscripcion:
    from vozflow.transcripcion.faster_whisper import MotorFasterWhisper, modelo_disponible

    if not modelo_disponible("small"):
        pytest.skip("El modelo small no está descargado")
    return MotorFasterWhisper(modelo="small")


@pytest.fixture(
    params=[
        pytest.param(MotorFalso, id="doble"),
        pytest.param(_motor_real, id="faster-whisper", marks=pytest.mark.lento),
    ]
)
def motor(request: pytest.FixtureRequest) -> Iterator[MotorDeTranscripcion]:
    fabrica: Callable[[], MotorDeTranscripcion] = request.param
    instancia = fabrica()
    yield instancia
    instancia.descargar()


@pytest.fixture
def sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier intento de abrir una conexión de red falla la prueba (RF-006)."""

    def _prohibido(*_: Any, **__: Any) -> None:
        raise AssertionError("El motor intentó usar la red")

    monkeypatch.setattr(socket.socket, "connect", _prohibido)
    monkeypatch.setattr(socket.socket, "connect_ex", _prohibido)


def _audio(segundos: float = 1.0) -> np.ndarray:
    t = np.arange(int(segundos * FRECUENCIA)) / FRECUENCIA
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


# ---- ciclo de vida ----------------------------------------------------------------


def test_transcribir_sin_cargar_es_un_error_claro(motor: MotorDeTranscripcion) -> None:
    with pytest.raises(ErrorDeTranscripcion, match="cargado"):
        motor.transcribir(_audio(), None, None)


def test_cargar_dos_veces_es_inofensivo(motor: MotorDeTranscripcion) -> None:
    motor.cargar()
    motor.cargar()

    assert isinstance(motor.transcribir(_audio(), None, None), Transcripcion)


def test_descargar_libera_el_motor_y_se_puede_volver_a_cargar(
    motor: MotorDeTranscripcion,
) -> None:
    motor.cargar()
    motor.descargar()

    with pytest.raises(ErrorDeTranscripcion):
        motor.transcribir(_audio(), None, None)
    motor.cargar()
    assert isinstance(motor.transcribir(_audio(), None, None), Transcripcion)


def test_descargar_sin_haber_cargado_no_falla(motor: MotorDeTranscripcion) -> None:
    motor.descargar()


# ---- resultado ----------------------------------------------------------------------


def test_devuelve_una_transcripcion_bien_formada(motor: MotorDeTranscripcion) -> None:
    motor.cargar()

    resultado = motor.transcribir(_audio(), None, None)

    assert isinstance(resultado.texto, str)
    assert isinstance(resultado.idioma, str)
    assert 0.0 <= resultado.probabilidad_idioma <= 1.0
    assert isinstance(resultado.duracion_ms, int)
    assert resultado.duracion_ms >= 0


def test_un_audio_vacio_da_texto_vacio(motor: MotorDeTranscripcion) -> None:
    motor.cargar()

    resultado = motor.transcribir(np.zeros(0, dtype=np.float32), None, None)

    assert resultado.texto == ""


def test_acepta_pista_e_idioma(motor: MotorDeTranscripcion) -> None:
    motor.cargar()

    resultado = motor.transcribir(_audio(), "SQLAlchemy, Alembic", "es")

    assert isinstance(resultado, Transcripcion)


# ---- entrada inválida -------------------------------------------------------------------


@pytest.mark.parametrize(
    "audio",
    [
        np.zeros(16000, dtype=np.int16),
        np.zeros(16000, dtype=np.float64),
        np.zeros((16000, 2), dtype=np.float32),
    ],
    ids=["enteros", "doble precisión", "estéreo"],
)
def test_rechaza_audio_que_no_es_float32_mono(
    motor: MotorDeTranscripcion, audio: np.ndarray
) -> None:
    motor.cargar()

    with pytest.raises(ErrorDeTranscripcion, match="float32"):
        motor.transcribir(audio, None, None)


# ---- sin red ---------------------------------------------------------------------------------


def test_transcribir_no_usa_la_red(motor: MotorDeTranscripcion, sin_red: None) -> None:
    motor.cargar()

    assert isinstance(motor.transcribir(_audio(), None, None), Transcripcion)
