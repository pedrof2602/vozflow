"""Contrato del motor de transcripción (contracts/puertos.md).

Un motor recibe audio ya capturado en memoria y devuelve texto. No abre archivos de audio y
no usa la red: el reconocimiento es siempre local (RF-006).
"""

from dataclasses import dataclass
from typing import Protocol

from vozflow.audio.senal import Audio

__all__ = [
    "Audio",
    "ErrorDeTranscripcion",
    "MotorDeTranscripcion",
    "Transcripcion",
    "validar_audio",
]


class ErrorDeTranscripcion(Exception):
    """El motor no pudo transcribir; el mensaje se puede mostrar tal cual."""


@dataclass(frozen=True)
class Transcripcion:
    texto: str
    idioma: str
    """Código del idioma detectado (``es``, ``en``); vacío si no hubo audio."""
    probabilidad_idioma: float
    duracion_ms: int
    """Tiempo que tardó el motor en transcribir."""
    no_voz_probabilidad: float = 0.0
    """La mayor probabilidad, entre los segmentos, de que no sea voz (0 a 1). Alta = sospechoso."""
    logprob_medio: float = 0.0
    """Confianza media del motor en lo que escribió; más cerca de 0 es más seguro."""


class MotorDeTranscripcion(Protocol):
    def cargar(self) -> None:
        """Deja el motor listo. Llamarlo más de una vez es inofensivo."""

    def transcribir(self, audio: Audio, pista: str | None, idioma: str | None) -> Transcripcion:
        """Transcribe ``audio`` (``float32``, mono, 16 kHz).

        ``pista`` son las palabras del diccionario personal; ``idioma`` nulo significa
        detección automática.
        """

    def descargar(self) -> None:
        """Libera la memoria del motor. Se puede volver a ``cargar``."""


def validar_audio(audio: Audio) -> None:
    """Rechaza lo que no sea un arreglo ``float32`` mono; lo exige todo motor."""
    if getattr(audio, "dtype", None) != "float32" or getattr(audio, "ndim", None) != 1:
        raise ErrorDeTranscripcion("El audio debe ser un arreglo float32 mono de 16 kHz")
