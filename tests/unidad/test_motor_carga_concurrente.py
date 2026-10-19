"""Cargar el modelo desde dos hilos a la vez lo carga una sola vez (002: el asistente y el arranque)."""

import threading
import time
from typing import Any

import pytest

from vozflow.transcripcion import faster_whisper as modulo
from vozflow.transcripcion.faster_whisper import MotorFasterWhisper


def test_dos_cargas_a_la_vez_cargan_el_modelo_una_sola_vez(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cargas: list[int] = []

    class ModeloFalso:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            cargas.append(1)
            time.sleep(0.1)  # da tiempo a que el segundo hilo llegue mientras el primero carga

    monkeypatch.setattr(modulo, "_ruta_local", lambda nombre: "/modelo")
    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", ModeloFalso)
    motor = MotorFasterWhisper("small")
    hilos = [threading.Thread(target=motor.cargar) for _ in range(4)]

    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert cargas == [1]
