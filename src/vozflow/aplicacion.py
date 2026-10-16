"""Une las piezas de vozflow. Por ahora, el dictado de una sola vez para la línea de comandos."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from vozflow.audio.senal import FRECUENCIA
from vozflow.dominio.tuberia import (
    OPCIONES_POR_DEFECTO,
    OpcionesDeTuberia,
    ResultadoProceso,
    procesar,
)
from vozflow.transcripcion.motor import MotorDeTranscripcion, Transcripcion
from vozflow.transcripcion.por_tramos import TranscriptorPorTramos

_registro = logging.getLogger(__name__)

INTERVALO_DE_REVISION_S = 1.0
"""Cada cuánto se revisa el audio grabado para mandar al motor los tramos cerrados."""


class Grabadora(Protocol):
    """Lo que ``dictar_una_vez`` necesita de la captura; ``Capturador`` lo cumple."""

    def iniciar(self, dispositivo: str | int | None = None) -> None: ...

    def audio_acumulado(self) -> npt.NDArray[np.int16]: ...

    def detener_crudo(self) -> npt.NDArray[np.int16]: ...


@dataclass(frozen=True)
class ResultadoDictado:
    transcripcion: Transcripcion
    """Lo que devolvió el motor, sin tocar."""
    procesado: ResultadoProceso
    """Después de la tubería de texto: comandos de voz, limpieza y puntuación."""
    segundos_grabados: float
    espera_tras_soltar_ms: int
    """Lo que tardó en tener el texto una vez terminada la grabación."""
    audio: npt.NDArray[np.int16]
    """Lo grabado, sin normalizar."""


def _dictar(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    mientras_graba: Callable[[Callable[[], None]], None],
    dispositivo: str | int | None,
    idioma: str | None,
    pista: str | None,
    opciones: OpcionesDeTuberia,
    al_empezar: Callable[[], None] | None,
) -> ResultadoDictado:
    """Esqueleto común: cargar, grabar, transcribir por tramos y procesar el texto.

    ``mientras_graba`` decide cuándo terminar; recibe una función ``revisar`` que debe llamar
    cada tanto para que los tramos ya cerrados se manden al motor.
    """
    motor.cargar()
    transcriptor = TranscriptorPorTramos(motor, idioma=idioma, pista=pista)
    try:
        grabadora.iniciar(dispositivo)
    except BaseException:
        transcriptor.cancelar(esperar=False)
        raise
    if al_empezar is not None:
        al_empezar()
    try:
        mientras_graba(lambda: transcriptor.actualizar(grabadora.audio_acumulado()))
    except BaseException:
        grabadora.detener_crudo()
        transcriptor.cancelar(esperar=False)
        raise
    crudo = grabadora.detener_crudo()
    try:
        transcripcion = transcriptor.terminar(crudo)
    except BaseException:
        transcriptor.cancelar(esperar=False)
        raise
    procesado = procesar(transcripcion.texto, idioma or transcripcion.idioma or None, opciones)
    return ResultadoDictado(
        transcripcion=transcripcion,
        procesado=procesado,
        segundos_grabados=len(crudo) / FRECUENCIA,
        espera_tras_soltar_ms=transcripcion.duracion_ms,
        audio=crudo,
    )


def dictar_una_vez(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    segundos: float,
    dispositivo: str | int | None = None,
    idioma: str | None = None,
    pista: str | None = None,
    opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO,
    esperar: Callable[[float], None] = time.sleep,
    al_empezar: Callable[[], None] | None = None,
) -> ResultadoDictado:
    """Graba ``segundos``, transcribe (por tramos, mientras graba) y procesa el texto.

    El motor se carga *antes* de abrir el micrófono: así un modelo que falta o tarda en cargar
    se descubre sin haber grabado nada.
    """

    def esperar_el_tiempo(revisar: Callable[[], None]) -> None:
        transcurrido = 0.0
        while transcurrido < segundos:
            tramo = min(INTERVALO_DE_REVISION_S, segundos - transcurrido)
            esperar(tramo)
            transcurrido += tramo
            revisar()

    return _dictar(
        grabadora=grabadora,
        motor=motor,
        mientras_graba=esperar_el_tiempo,
        dispositivo=dispositivo,
        idioma=idioma,
        pista=pista,
        opciones=opciones,
        al_empezar=al_empezar,
    )


def dictar_hasta(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    seguir: Callable[[], bool],
    esperar: Callable[[float], None] = time.sleep,
    dispositivo: str | int | None = None,
    idioma: str | None = None,
    pista: str | None = None,
    opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO,
    al_empezar: Callable[[], None] | None = None,
) -> ResultadoDictado:
    """Como ``dictar_una_vez``, pero graba mientras ``seguir()`` sea verdadero."""

    def esperar_el_evento(revisar: Callable[[], None]) -> None:
        while seguir():
            esperar(INTERVALO_DE_REVISION_S)
            revisar()

    return _dictar(
        grabadora=grabadora,
        motor=motor,
        mientras_graba=esperar_el_evento,
        dispositivo=dispositivo,
        idioma=idioma,
        pista=pista,
        opciones=opciones,
        al_empezar=al_empezar,
    )
