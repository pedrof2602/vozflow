"""Medidas básicas de la señal de audio, compartidas por la normalización y el corte."""

import numpy as np
import numpy.typing as npt

Audio = npt.NDArray[np.float32]

FRECUENCIA = 16_000
"""Frecuencia de muestreo con la que trabaja todo vozflow (Hz)."""

TRAMA = 320
"""Muestras por trama de análisis: 20 ms a 16 kHz."""

UMBRAL_RMS = 0.003
"""Nivel eficaz por encima del cual una trama se considera voz.

Medido en el equipo de Pedro: el ruido de una habitación en silencio da ~0,0004 y una voz
normal con la entrada al 27 % supera 0,005, así que el umbral queda entre ambos.
"""


def audio_vacio() -> Audio:
    return np.zeros(0, dtype=np.float32)


def nivel_eficaz_por_trama(audio: Audio) -> npt.NDArray[np.float64]:
    """Nivel eficaz (RMS) de cada trama completa de 20 ms."""
    tramas = len(audio) // TRAMA
    if tramas == 0:
        return np.zeros(0, dtype=np.float64)
    bloques = audio[: tramas * TRAMA].reshape(tramas, TRAMA).astype(np.float64)
    return np.sqrt((bloques**2).mean(axis=1))
