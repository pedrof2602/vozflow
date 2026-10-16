"""Motor de transcripción con faster-whisper, en CPU.

Configuración elegida midiendo en el equipo de Pedro (research.md, sección 1): modelo ``small``
con cuantización int8, 4 hilos (el equipo tiene 4 núcleos físicos; con 8 hilos fue más lento)
y decodificación voraz (``beam_size=1``).
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from vozflow.audio.senal import Audio
from vozflow.transcripcion.motor import ErrorDeTranscripcion, Transcripcion, validar_audio

_registro = logging.getLogger(__name__)

MODELO_POR_DEFECTO = "small"
HILOS_POR_DEFECTO = 4
IDIOMAS_POR_DEFECTO = ("es", "en")
"""Idiomas que usa Pedro. La detección automática de Whisper elige entre ~99 y, ante ruido,
suele inventar uno (se observó hindi sobre el ruido de la habitación)."""


def _ruta_local(nombre: str) -> str | None:
    """Carpeta del modelo si ya está descargado; ``None`` si no."""
    from faster_whisper import download_model

    try:
        return str(download_model(nombre, local_files_only=True))
    except Exception:  # sin descargar, nombre desconocido o caché dañada
        return None


def modelo_disponible(nombre: str = MODELO_POR_DEFECTO) -> bool:
    """El modelo está en el equipo y se puede usar sin internet."""
    return _ruta_local(nombre) is not None


def descargar_modelo(nombre: str = MODELO_POR_DEFECTO) -> str:
    """Descarga el modelo una sola vez; es lo único que necesita internet. Devuelve su carpeta."""
    from faster_whisper import download_model

    try:
        return str(download_model(nombre))
    except Exception as error:
        raise ErrorDeTranscripcion(f"No se pudo descargar el modelo '{nombre}': {error}") from error


@dataclass(frozen=True)
class _Pasada:
    texto: str
    info: Any
    no_voz_probabilidad: float
    logprob_medio: float


def _logprob_ponderado(segmentos: list[Any]) -> float:
    """Confianza media de los segmentos, ponderada por lo que dura cada uno."""
    duraciones = [max(float(s.end) - float(s.start), 1e-6) for s in segmentos]
    if not segmentos:
        return 0.0
    return sum(float(s.avg_logprob) * d for s, d in zip(segmentos, duraciones, strict=True)) / sum(
        duraciones
    )


class MotorFasterWhisper:
    """``MotorDeTranscripcion`` local y sin red: usa solo el modelo ya descargado."""

    def __init__(
        self,
        modelo: str = MODELO_POR_DEFECTO,
        hilos: int = HILOS_POR_DEFECTO,
        idiomas_permitidos: tuple[str, ...] = IDIOMAS_POR_DEFECTO,
    ) -> None:
        self._nombre = modelo
        self._hilos = hilos
        self._permitidos = idiomas_permitidos
        self._modelo: Any = None

    def cargar(self) -> None:
        if self._modelo is not None:
            return
        ruta = _ruta_local(self._nombre)
        if ruta is None:
            raise ErrorDeTranscripcion(
                f"El modelo '{self._nombre}' no está descargado. "
                "Descargalo una vez con: uv run python -m vozflow descargar-modelo"
            )
        from faster_whisper import WhisperModel

        inicio = time.perf_counter()
        try:
            self._modelo = WhisperModel(
                ruta,
                device="cpu",
                compute_type="int8",
                cpu_threads=self._hilos,
                local_files_only=True,
            )
        except Exception as error:
            raise ErrorDeTranscripcion(f"No se pudo cargar el modelo: {error}") from error
        _registro.info("Modelo %s cargado en %.1f s", self._nombre, time.perf_counter() - inicio)

    def transcribir(self, audio: Audio, pista: str | None, idioma: str | None) -> Transcripcion:
        if self._modelo is None:
            raise ErrorDeTranscripcion("El motor no está cargado")
        validar_audio(audio)
        if len(audio) == 0:
            return Transcripcion(texto="", idioma="", probabilidad_idioma=0.0, duracion_ms=0)
        inicio = time.perf_counter()
        pedido = idioma.split("-")[0].lower() if idioma else None
        try:
            pasada = self._pasada(audio, pista, pedido)
            probabilidad = float(pasada.info.language_probability)
            if pedido is None and pasada.info.language not in self._permitidos:
                # Idioma inventado (ruido): se vuelve a transcribir en el permitido más probable.
                elegido, probabilidad = self._elegir_permitido(pasada.info.all_language_probs)
                pasada = self._pasada(audio, pista, elegido)
        except Exception as error:
            raise ErrorDeTranscripcion(f"Falló la transcripción: {error}") from error
        milisegundos = max(1, round((time.perf_counter() - inicio) * 1000))
        return Transcripcion(
            texto=pasada.texto,
            idioma=str(pasada.info.language),
            probabilidad_idioma=probabilidad,
            duracion_ms=milisegundos,
            no_voz_probabilidad=pasada.no_voz_probabilidad,
            logprob_medio=pasada.logprob_medio,
        )

    def _pasada(self, audio: Audio, pista: str | None, idioma: str | None) -> _Pasada:
        segmentos, info = self._modelo.transcribe(
            audio,  # arreglo float32: no se decodifica ningún archivo
            beam_size=1,
            language=idioma,
            vad_filter=False,
            initial_prompt=pista,
            condition_on_previous_text=False,
        )
        # transcribe() devuelve un generador: el trabajo ocurre al recorrerlo.
        lista = list(segmentos)
        texto = " ".join(segmento.text.strip() for segmento in lista).strip()
        return _Pasada(
            texto=texto,
            info=info,
            no_voz_probabilidad=max((float(s.no_speech_prob) for s in lista), default=0.0),
            logprob_medio=_logprob_ponderado(lista),
        )

    def _elegir_permitido(self, todas: list[tuple[str, float]] | None) -> tuple[str, float]:
        """El idioma permitido más probable y su probabilidad entre los permitidos."""
        probabilidades = dict(todas or [])
        elegido = max(self._permitidos, key=lambda c: probabilidades.get(c, 0.0))
        total = sum(probabilidades.get(c, 0.0) for c in self._permitidos)
        if total <= 0:
            return self._permitidos[0], 0.0
        return elegido, probabilidades[elegido] / total

    def descargar(self) -> None:
        self._modelo = None
