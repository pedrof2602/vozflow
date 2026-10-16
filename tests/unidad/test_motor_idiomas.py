"""Restricción de idiomas del motor: solo español e inglés (los que usa Pedro).

La detección automática de Whisper elige entre ~99 idiomas y, ante ruido, suele inventar uno
(se observó hindi sobre el ruido de la habitación). Se prueba con un modelo falso.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from vozflow.audio.senal import FRECUENCIA
from vozflow.transcripcion.faster_whisper import MotorFasterWhisper


@dataclass
class ModeloFalso:
    """Imita ``WhisperModel.transcribe``: responde según el idioma que se le pida."""

    detectado: str
    probabilidades: list[tuple[str, float]] | None
    textos: dict[str | None, str]
    llamadas: list[dict[str, Any]] = field(default_factory=list)
    # (no_speech_prob, avg_logprob, duración en segundos) de cada segmento que devuelve
    metricas: list[tuple[float, float, float]] = field(default_factory=lambda: [(0.05, -0.3, 1.0)])

    def transcribir(self, audio: Any, **argumentos: Any) -> Any:
        self.llamadas.append(argumentos)
        idioma = argumentos.get("language")
        forzado = idioma is not None
        informacion = SimpleNamespace(
            language=idioma or self.detectado,
            language_probability=1.0
            if forzado
            else dict(self.probabilidades or []).get(self.detectado, 0.5),
            all_language_probs=None if forzado else self.probabilidades,
        )
        segmentos = [
            SimpleNamespace(
                text=f" {self.textos.get(idioma or self.detectado, '?')} ",
                no_speech_prob=prob,
                avg_logprob=logprob,
                start=0.0,
                end=duracion,
            )
            for prob, logprob, duracion in self.metricas
        ]
        return iter(segmentos), informacion


class _Contenedor:
    def __init__(self, modelo: ModeloFalso) -> None:
        self.transcribe = modelo.transcribir


def _motor(modelo: ModeloFalso, permitidos: tuple[str, ...] = ("es", "en")) -> MotorFasterWhisper:
    motor = MotorFasterWhisper(idiomas_permitidos=permitidos)
    motor._modelo = _Contenedor(modelo)  # evita cargar el modelo real
    return motor


def _audio() -> np.ndarray:
    return np.full(FRECUENCIA, 0.1, dtype=np.float32)


def test_si_se_detecta_un_idioma_permitido_no_se_repite_la_pasada() -> None:
    modelo = ModeloFalso("es", [("es", 0.9), ("en", 0.05)], {"es": "hola"})
    motor = _motor(modelo)

    resultado = motor.transcribir(_audio(), None, None)

    assert len(modelo.llamadas) == 1
    assert resultado.idioma == "es"
    assert resultado.texto == "hola"


def test_si_se_detecta_otro_idioma_se_reintenta_con_el_permitido_mas_probable() -> None:
    probs = [("hi", 0.40), ("es", 0.35), ("en", 0.10)]
    modelo = ModeloFalso("hi", probs, {"hi": "बराके", "es": "es un ruido"})
    motor = _motor(modelo)

    resultado = motor.transcribir(_audio(), None, None)

    assert [llamada.get("language") for llamada in modelo.llamadas] == [None, "es"]
    assert resultado.idioma == "es"
    assert resultado.texto == "es un ruido"  # nunca queda el texto en hindi


def test_elige_ingles_si_es_el_permitido_mas_probable() -> None:
    probs = [("ru", 0.5), ("en", 0.3), ("es", 0.1)]
    modelo = ModeloFalso("ru", probs, {"en": "some noise"})

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.idioma == "en"


def test_la_probabilidad_se_calcula_entre_los_idiomas_permitidos() -> None:
    probs = [("hi", 0.40), ("es", 0.30), ("en", 0.10)]
    modelo = ModeloFalso("hi", probs, {"es": "x"})

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.probabilidad_idioma == pytest.approx(0.30 / 0.40)


def test_sin_probabilidades_se_usa_el_primer_idioma_permitido() -> None:
    modelo = ModeloFalso("hi", None, {"es": "x"})

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.idioma == "es"


def test_un_idioma_pedido_expresamente_se_respeta_sin_reintentos() -> None:
    modelo = ModeloFalso("hi", None, {"fr": "bonjour"})

    resultado = _motor(modelo).transcribir(_audio(), None, "fr")

    assert len(modelo.llamadas) == 1
    assert resultado.idioma == "fr"


def test_el_idioma_con_region_cuenta_como_su_idioma_base() -> None:
    modelo = ModeloFalso("es", [("es", 0.9)], {"es": "hola"})

    _motor(modelo).transcribir(_audio(), None, "es-AR")

    assert modelo.llamadas[0]["language"] == "es"


def test_se_puede_ampliar_la_lista_de_idiomas_permitidos() -> None:
    modelo = ModeloFalso("fr", [("fr", 0.9), ("es", 0.05)], {"fr": "bonjour"})

    resultado = _motor(modelo, permitidos=("es", "en", "fr")).transcribir(_audio(), None, None)

    assert len(modelo.llamadas) == 1
    assert resultado.idioma == "fr"


def test_la_duracion_incluye_el_reintento() -> None:
    modelo = ModeloFalso("hi", [("hi", 0.5), ("es", 0.4)], {"es": "x"})

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.duracion_ms >= 1


# ---- confianza de la transcripción ---------------------------------------------------------


def test_expone_la_probabilidad_maxima_de_no_haber_voz_y_el_logprob_medio() -> None:
    modelo = ModeloFalso(
        "es",
        [("es", 0.9)],
        {"es": "hola"},
        metricas=[(0.10, -0.2, 1.0), (0.40, -0.8, 1.0)],
    )

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.no_voz_probabilidad == pytest.approx(0.40)
    assert resultado.logprob_medio == pytest.approx(-0.5)


def test_el_logprob_medio_se_pondera_por_la_duracion_de_cada_segmento() -> None:
    modelo = ModeloFalso(
        "es",
        [("es", 0.9)],
        {"es": "hola"},
        metricas=[(0.0, -0.2, 3.0), (0.0, -1.0, 1.0)],
    )

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.logprob_medio == pytest.approx((-0.2 * 3 + -1.0 * 1) / 4)


def test_sin_segmentos_la_confianza_queda_en_cero() -> None:
    modelo = ModeloFalso("es", [("es", 0.9)], {"es": ""}, metricas=[])

    resultado = _motor(modelo).transcribir(_audio(), None, None)

    assert resultado.texto == ""
    assert resultado.no_voz_probabilidad == 0.0
    assert resultado.logprob_medio == 0.0
