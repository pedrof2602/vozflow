"""Pruebas con el modelo real (marca ``lento``): ``uv run pytest -m lento``.

Usan voz sintética de ``espeak-ng``, así que miden que el motor funcione (idioma, tipo de
dato, sin red), no la calidad de reconocimiento con la voz de Pedro; eso lo mide ``medir``.
"""

import shutil
import socket
import subprocess
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vozflow.audio.senal import FRECUENCIA, Audio
from vozflow.transcripcion.faster_whisper import MotorFasterWhisper, modelo_disponible

pytestmark = pytest.mark.lento

if shutil.which("espeak-ng") is None:
    pytest.skip("Falta espeak-ng para generar voz de prueba", allow_module_level=True)
if not modelo_disponible("small"):
    pytest.skip("El modelo small no está descargado", allow_module_level=True)


def _hablar(tmp_path: Path, voz: str, frase: str) -> Audio:
    """Genera voz sintética y la devuelve como float32 mono a 16 kHz."""
    archivo = tmp_path / "voz.wav"
    subprocess.run(["espeak-ng", "-v", voz, "-s", "150", "-w", str(archivo), frase], check=True)
    with wave.open(str(archivo)) as wav:
        muestras = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        origen = wav.getframerate()
    audio = muestras.astype(np.float32) / 32768.0
    if origen != FRECUENCIA:
        instantes = np.arange(0, len(audio) / origen, 1 / FRECUENCIA)
        audio = np.interp(instantes, np.arange(len(audio)) / origen, audio).astype(np.float32)
    return audio


@pytest.fixture(scope="module")
def motor() -> Iterator[MotorFasterWhisper]:
    instancia = MotorFasterWhisper(modelo="small")
    instancia.cargar()
    yield instancia
    instancia.descargar()


def test_detecta_espanol(motor: MotorFasterWhisper, tmp_path: Path) -> None:
    audio = _hablar(
        tmp_path, "es", "Necesito que revises el código antes de las cinco de la tarde."
    )

    resultado = motor.transcribir(audio, None, None)

    assert resultado.idioma == "es"
    assert resultado.probabilidad_idioma > 0.5
    assert "cinco de la tarde" in resultado.texto.lower()


def test_detecta_ingles(motor: MotorFasterWhisper, tmp_path: Path) -> None:
    audio = _hablar(
        tmp_path, "en-us", "Please open the pull request and check that the tests are passing."
    )

    resultado = motor.transcribir(audio, None, None)

    assert resultado.idioma == "en"
    assert "tests are passing" in resultado.texto.lower()


def test_el_idioma_indicado_manda_sobre_la_deteccion(
    motor: MotorFasterWhisper, tmp_path: Path
) -> None:
    audio = _hablar(tmp_path, "es", "Necesito que revises el código antes de las cinco.")

    resultado = motor.transcribir(audio, None, "es")

    assert resultado.idioma == "es"
    assert resultado.probabilidad_idioma == pytest.approx(1.0)


def test_le_pasa_al_modelo_un_arreglo_float32_y_no_un_archivo(
    motor: MotorFasterWhisper, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pasar un arreglo evita decodificar archivos con PyAV (que falla con PyAV 19)."""
    recibido: dict[str, Any] = {}
    original = motor._modelo.transcribe

    def espia(audio: Any, **argumentos: Any) -> Any:
        recibido["audio"] = audio
        recibido["argumentos"] = argumentos
        return original(audio, **argumentos)

    monkeypatch.setattr(motor._modelo, "transcribe", espia)
    audio = _hablar(tmp_path, "es", "Hola, esto es una prueba de dictado.")

    motor.transcribir(audio, "SQLAlchemy", "es")

    assert isinstance(recibido["audio"], np.ndarray)
    assert recibido["audio"].dtype == np.float32
    argumentos = recibido["argumentos"]
    assert argumentos["beam_size"] == 1
    assert argumentos["vad_filter"] is False
    assert argumentos["initial_prompt"] == "SQLAlchemy"
    assert argumentos["language"] == "es"


def test_funciona_sin_red_y_con_el_modo_sin_conexion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RF-006 y RF-009: con el modelo ya descargado no hace falta internet."""

    def prohibido(*_: Any, **__: Any) -> None:
        raise AssertionError("El motor intentó usar la red")

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido)
    audio = _hablar(tmp_path, "es", "Hola, esto es una prueba sin conexión.")
    aislado = MotorFasterWhisper(modelo="small")

    aislado.cargar()
    try:
        resultado = aislado.transcribir(audio, None, None)
    finally:
        aislado.descargar()

    assert resultado.texto.strip() != ""


def test_el_texto_viene_sin_espacios_sobrantes_en_los_bordes(
    motor: MotorFasterWhisper, tmp_path: Path
) -> None:
    audio = _hablar(tmp_path, "es", "Hola, esto es una prueba de dictado.")

    resultado = motor.transcribir(audio, None, None)

    assert resultado.texto == resultado.texto.strip()


def test_la_transcripcion_informa_cuanto_tardo(motor: MotorFasterWhisper, tmp_path: Path) -> None:
    audio = _hablar(tmp_path, "es", "Hola, esto es una prueba de dictado.")

    resultado = motor.transcribir(audio, None, None)

    assert resultado.duracion_ms > 0
