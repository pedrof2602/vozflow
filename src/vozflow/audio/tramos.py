"""Corte del audio en tramos por silencios largos.

Sirve para transcribir un dictado largo por partes mientras la persona sigue hablando: los
tramos ya cerrados se mandan al motor y al soltar la tecla solo queda el último.
"""

import math

from vozflow.audio.senal import FRECUENCIA, TRAMA, UMBRAL_RMS, Audio, nivel_eficaz_por_trama

SILENCIO_MINIMO_S = 0.8
"""Un silencio más corto que esto es una pausa entre palabras y no se corta."""

TRAMO_MINIMO_S = 1.0
"""Ningún tramo dura menos que esto: el motor rinde mal con fragmentos tan cortos."""


def _cortes_en_silencios_largos(audio: Audio) -> list[int]:
    """Muestra central de cada silencio largo que está entre dos tramos de voz."""
    silenciosa = nivel_eficaz_por_trama(audio) < UMBRAL_RMS
    minimo = math.ceil(SILENCIO_MINIMO_S * FRECUENCIA / TRAMA)
    cortes: list[int] = []
    total = len(silenciosa)
    i = 0
    while i < total:
        if not silenciosa[i]:
            i += 1
            continue
        j = i
        while j < total and silenciosa[j]:
            j += 1
        # El silencio del principio o del final no separa dos frases: no se corta.
        if j - i >= minimo and i > 0 and j < total:
            cortes.append((i + (j - i) // 2) * TRAMA)
        i = j
    return cortes


def _unir_tramos_cortos(tramos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    minimo = int(TRAMO_MINIMO_S * FRECUENCIA)
    unidos = list(tramos)
    while len(unidos) > 1:
        corto = next((k for k, (a, b) in enumerate(unidos) if b - a < minimo), None)
        if corto is None:
            break
        inicio, fin = unidos[corto]
        if corto > 0:
            unidos[corto - 1] = (unidos[corto - 1][0], fin)
        else:
            unidos[1] = (inicio, unidos[1][1])
        del unidos[corto]
    return unidos


def cortar_por_silencio(audio: Audio) -> list[tuple[int, int]]:
    """Divide el audio en tramos ``(inicio, fin)`` en muestras, cortando a mitad de cada silencio.

    Los tramos son contiguos y cubren todo el audio. El último es el que aún puede estar
    abierto (la persona podría seguir hablando).
    """
    if len(audio) == 0:
        return []
    limites = [0, *_cortes_en_silencios_largos(audio), len(audio)]
    tramos = list(zip(limites, limites[1:], strict=False))
    return _unir_tramos_cortos(tramos)
