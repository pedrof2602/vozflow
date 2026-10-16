"""Dobles de prueba compartidos por varias baterías."""

from dataclasses import dataclass
from typing import Final

from vozflow.audio.senal import Audio
from vozflow.transcripcion.motor import ErrorDeTranscripcion, Transcripcion, validar_audio

_MENSAJE_NO_CARGADO: Final = "El motor no está cargado"


@dataclass(frozen=True)
class LlamadaATranscribir:
    muestras: int
    pista: str | None
    idioma: str | None


class MotorFalso:
    """Motor de transcripción que devuelve un texto fijo; cumple el contrato de ``motor.py``."""

    def __init__(
        self,
        texto: str = "hola mundo",
        idioma: str = "es",
        probabilidad_idioma: float = 0.99,
    ) -> None:
        self.texto = texto
        self.idioma = idioma
        self.probabilidad_idioma = probabilidad_idioma
        self.llamadas: list[LlamadaATranscribir] = []
        self.veces_cargado = 0
        self.cargado = False

    def cargar(self) -> None:
        self.cargado = True
        self.veces_cargado += 1

    def transcribir(self, audio: Audio, pista: str | None, idioma: str | None) -> Transcripcion:
        if not self.cargado:
            raise ErrorDeTranscripcion(_MENSAJE_NO_CARGADO)
        validar_audio(audio)
        self.llamadas.append(LlamadaATranscribir(len(audio), pista, idioma))
        if len(audio) == 0:
            return Transcripcion(texto="", idioma="", probabilidad_idioma=0.0, duracion_ms=0)
        return Transcripcion(
            texto=self.texto,
            idioma=idioma or self.idioma,
            probabilidad_idioma=self.probabilidad_idioma,
            duracion_ms=1,
        )

    def descargar(self) -> None:
        self.cargado = False
