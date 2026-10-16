"""Captura de audio del micrófono y su preparación para el motor de transcripción."""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from vozflow.audio.senal import (
    FRECUENCIA,
    TRAMA,
    UMBRAL_RMS,
    Audio,
    audio_vacio,
    nivel_eficaz_por_trama,
)

DURACION_MINIMA_S = 0.5
"""Un audio más corto que esto se descarta (RF-028, caso límite)."""

PICO_OBJETIVO = 0.9
"""Pico al que se lleva el audio antes de transcribir."""

GANANCIA_MAXIMA = 100.0
"""Tope de amplificación (40 dB): evita convertir ruido en señal."""

TRAMAS_MINIMAS_DE_VOZ = 5
"""Tramas de 20 ms (100 ms) con nivel de voz para considerar que hubo voz."""

DURACION_MAXIMA_S = 600.0
"""Tope de una grabación: protege la memoria si la tecla queda apretada."""

_PISO_DEL_NIVEL_DB = 60.0
"""El indicador muestra de -60 dB (0.0) a 0 dB (1.0)."""

_registro = logging.getLogger(__name__)

__all__ = [
    "DURACION_MAXIMA_S",
    "DURACION_MINIMA_S",
    "FRECUENCIA",
    "GANANCIA_MAXIMA",
    "PICO_OBJETIVO",
    "TRAMA",
    "a_float32",
    "normalizar",
    "tiene_voz",
]


def a_float32(muestras: npt.NDArray[np.generic]) -> Audio:
    """Convierte a ``float32`` entre -1 y 1 y a mono (promedia los canales)."""
    if np.issubdtype(muestras.dtype, np.signedinteger):
        # Enteros con signo (int16 del micrófono): el rango es de -2^(bits-1) a 2^(bits-1) - 1.
        escala = float(2 ** (8 * muestras.dtype.itemsize - 1))
        convertido = muestras.astype(np.float32) / np.float32(escala)
    else:
        convertido = muestras.astype(np.float32)
    if convertido.ndim == 2:
        convertido = convertido.mean(axis=1, dtype=np.float32)
    limpio: Audio = np.nan_to_num(convertido, nan=0.0, posinf=1.0, neginf=-1.0)
    return limpio.astype(np.float32)


def tiene_voz(audio: Audio) -> bool:
    """Hay voz si al menos 100 ms de tramas superan el nivel de ruido de fondo."""
    niveles = nivel_eficaz_por_trama(audio)
    return int((niveles >= UMBRAL_RMS).sum()) >= TRAMAS_MINIMAS_DE_VOZ


def normalizar(muestras: npt.NDArray[np.generic]) -> Audio:
    """Prepara el audio para transcribir: mono, ``float32`` y con el pico en el objetivo.

    Devuelve audio vacío si dura menos de ``DURACION_MINIMA_S`` o no tiene voz; así el ruido de
    fondo nunca se amplifica hasta parecer una frase.
    """
    audio = a_float32(muestras)
    if audio.size < DURACION_MINIMA_S * FRECUENCIA or not tiene_voz(audio):
        return audio_vacio()
    pico = float(np.abs(audio).max())
    ganancia = min(PICO_OBJETIVO / pico, GANANCIA_MAXIMA)
    return (audio * np.float32(ganancia)).astype(np.float32)


# ---- captura ----------------------------------------------------------------


class ErrorDeAudio(Exception):
    """El micrófono no se pudo abrir o arrancar; el mensaje se puede mostrar tal cual."""


@dataclass(frozen=True)
class Dispositivo:
    indice: int
    nombre: str
    canales_de_entrada: int
    es_predeterminado: bool


def _importar_sounddevice() -> Any:
    try:
        import sounddevice
    except OSError as error:  # falta la biblioteca PortAudio del sistema
        raise ErrorDeAudio(
            f"No se pudo cargar PortAudio, necesario para usar el micrófono: {error}"
        ) from error
    return sounddevice


def nivel_de_bloque(bloque: npt.NDArray[np.generic]) -> float:
    """Nivel de un bloque para el indicador, entre 0.0 (silencio) y 1.0 (máximo)."""
    if bloque.size == 0:
        return 0.0
    muestras = a_float32(bloque.reshape(-1))
    eficaz = float(np.sqrt(np.mean(muestras.astype(np.float64) ** 2)))
    decibelios = 20.0 * np.log10(max(eficaz, 1e-9))
    return float(np.clip((decibelios + _PISO_DEL_NIVEL_DB) / _PISO_DEL_NIVEL_DB, 0.0, 1.0))


def listar_dispositivos(sd: Any = None) -> list[Dispositivo]:
    """Dispositivos con entrada de audio (RF-005), marcando el predeterminado."""
    sd = sd if sd is not None else _importar_sounddevice()
    try:
        predeterminado: int | None = int(sd.query_devices(kind="input")["index"])
    except sd.PortAudioError, ValueError, KeyError:
        predeterminado = None
    return [
        Dispositivo(
            indice=int(d["index"]),
            nombre=str(d["name"]),
            canales_de_entrada=int(d["max_input_channels"]),
            es_predeterminado=int(d["index"]) == predeterminado,
        )
        for d in sd.query_devices()
        if d["max_input_channels"] > 0
    ]


class Capturador:
    """Graba del micrófono a 16 kHz, mono y 16 bits, y entrega el audio listo para transcribir.

    El audio llega desde el hilo de PortAudio; el búfer está protegido por un candado.
    """

    def __init__(
        self,
        sd: Any = None,
        al_nivel: Callable[[float], None] | None = None,
        duracion_maxima_s: float = DURACION_MAXIMA_S,
    ) -> None:
        self._sd = sd if sd is not None else _importar_sounddevice()
        self._al_nivel = al_nivel
        self._maximo_de_muestras = int(duracion_maxima_s * FRECUENCIA)
        self._candado = threading.Lock()
        self._flujo: Any = None
        self._activo = False
        self._bloques: list[npt.NDArray[np.int16]] = []
        self._muestras = 0
        self._nivel = 0.0
        self._truncado = False

    @property
    def grabando(self) -> bool:
        return self._flujo is not None

    @property
    def nivel(self) -> float:
        """Nivel del último bloque, entre 0.0 y 1.0."""
        return self._nivel

    @property
    def truncado(self) -> bool:
        """La última grabación llegó al máximo y se cortó."""
        return self._truncado

    def iniciar(self, dispositivo: str | int | None = None) -> None:
        if self._flujo is not None:
            raise RuntimeError("La captura ya está iniciada")
        with self._candado:
            self._bloques = []
            self._muestras = 0
            self._truncado = False
        self._nivel = 0.0
        flujo = None
        self._activo = True
        try:
            flujo = self._sd.InputStream(
                samplerate=FRECUENCIA,
                channels=1,
                dtype="int16",
                device=dispositivo,
                callback=self._al_recibir,
            )
            flujo.start()
        except (self._sd.PortAudioError, ValueError) as error:
            self._activo = False
            if flujo is not None:
                self._cerrar(flujo)
            raise ErrorDeAudio(f"No se pudo abrir el micrófono: {error}") from error
        self._flujo = flujo

    def audio_acumulado(self) -> npt.NDArray[np.int16]:
        """Lo grabado hasta ahora, sin detener la grabación."""
        with self._candado:
            if not self._bloques:
                return np.zeros(0, dtype=np.int16)
            return np.concatenate(self._bloques)

    def detener(self) -> Audio:
        """Detiene la grabación y devuelve el audio normalizado (vacío si no hay voz)."""
        return normalizar(self.detener_crudo())

    def detener_crudo(self) -> npt.NDArray[np.int16]:
        """Detiene la grabación y devuelve las muestras tal como llegaron, sin normalizar."""
        flujo, self._flujo = self._flujo, None
        if flujo is None:
            return np.zeros(0, dtype=np.int16)
        self._activo = False
        try:
            flujo.stop()
        except Exception:
            _registro.exception("No se pudo detener el flujo de audio limpiamente")
        finally:
            self._cerrar(flujo)
        with self._candado:
            muestras = np.concatenate(self._bloques) if self._bloques else np.zeros(0, np.int16)
            self._bloques = []
            self._muestras = 0
        self._avisar_nivel(0.0)
        return muestras

    @staticmethod
    def _cerrar(flujo: Any) -> None:
        try:
            flujo.close()
        except Exception:
            _registro.exception("No se pudo cerrar el flujo de audio")

    def _avisar_nivel(self, nivel: float) -> None:
        self._nivel = nivel
        if self._al_nivel is None:
            return
        try:
            self._al_nivel(nivel)
        except Exception:
            _registro.exception("Falló el aviso de nivel de audio")

    def _al_recibir(
        self, indata: npt.NDArray[np.int16], frames: int, tiempo: Any, estado: Any
    ) -> None:
        """Llamado por PortAudio en su propio hilo para cada bloque. No debe lanzar errores."""
        if not self._activo:
            return
        if getattr(estado, "input_overflow", False):
            _registro.warning("Se perdió audio por desbordamiento de entrada")
        # PortAudio reutiliza el búfer de ``indata``: hay que copiarlo.
        bloque = np.array(indata[:, 0] if indata.ndim == 2 else indata, dtype=np.int16, copy=True)
        with self._candado:
            libres = self._maximo_de_muestras - self._muestras
            if libres <= 0:
                self._truncado = True
                return
            if len(bloque) > libres:
                bloque = bloque[:libres]
                self._truncado = True
            self._bloques.append(bloque)
            self._muestras += len(bloque)
        self._avisar_nivel(nivel_de_bloque(bloque))
