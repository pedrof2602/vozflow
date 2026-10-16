import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from vozflow.audio.captura import (
    DURACION_MINIMA_S,
    FRECUENCIA,
    GANANCIA_MAXIMA,
    PICO_OBJETIVO,
    a_float32,
    normalizar,
    tiene_voz,
)

RUIDO = np.random.default_rng(1234)


def _seno(amplitud: float, segundos: float, hz: float = 220.0) -> np.ndarray:
    t = np.arange(int(segundos * FRECUENCIA)) / FRECUENCIA
    return (amplitud * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _ruido(sigma: float, segundos: float) -> np.ndarray:
    return RUIDO.normal(0.0, sigma, int(segundos * FRECUENCIA)).astype(np.float32)


# ---- conversión ------------------------------------------------------------


def test_a_float32_escala_enteros_de_16_bits_a_menos_uno_y_uno() -> None:
    muestras = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)

    resultado = a_float32(muestras)

    assert resultado.dtype == np.float32
    np.testing.assert_allclose(resultado, [0.0, 0.5, -0.5, 32767 / 32768, -1.0])


def test_a_float32_pasa_a_mono_promediando_los_canales() -> None:
    estereo = np.array([[0.2, 0.4], [-0.2, -0.6]], dtype=np.float32)

    resultado = a_float32(estereo)

    assert resultado.shape == (2,)
    np.testing.assert_allclose(resultado, [0.3, -0.4], atol=1e-6)


# ---- detección de voz --------------------------------------------------------


def test_una_voz_normal_tiene_voz() -> None:
    assert tiene_voz(_seno(0.05, 1.0)) is True


def test_una_voz_muy_baja_por_la_ganancia_del_microfono_sigue_siendo_voz() -> None:
    # Con la entrada al 27 % (como en el equipo de Pedro) la voz llega con poco nivel.
    assert tiene_voz(_seno(0.02, 1.0)) is True


def test_el_ruido_de_fondo_de_una_habitacion_en_silencio_no_es_voz() -> None:
    # Medido en el equipo de Pedro: nivel eficaz de ~12 sobre 32768 (0,0004).
    assert tiene_voz(_ruido(0.0004, 2.0)) is False


def test_el_silencio_digital_y_el_audio_vacio_no_son_voz() -> None:
    assert tiene_voz(np.zeros(FRECUENCIA, dtype=np.float32)) is False
    assert tiene_voz(np.zeros(0, dtype=np.float32)) is False


def test_un_golpe_corto_no_es_voz() -> None:
    audio = _ruido(0.0004, 1.0)
    audio[8000:8160] = 0.5  # 10 ms

    assert tiene_voz(audio) is False


# ---- normalización -----------------------------------------------------------


def test_lleva_el_pico_al_objetivo() -> None:
    resultado = normalizar(_seno(0.2, 1.0))

    assert resultado.dtype == np.float32
    assert resultado.ndim == 1
    assert float(np.abs(resultado).max()) == pytest.approx(PICO_OBJETIVO, abs=1e-4)


def test_normaliza_enteros_de_16_bits() -> None:
    muestras = (_seno(0.1, 1.0) * 32768).astype(np.int16)

    resultado = normalizar(muestras)

    assert float(np.abs(resultado).max()) == pytest.approx(PICO_OBJETIVO, abs=1e-3)


def test_baja_el_volumen_de_un_audio_muy_fuerte() -> None:
    resultado = normalizar(_seno(1.0, 1.0))

    assert float(np.abs(resultado).max()) == pytest.approx(PICO_OBJETIVO, abs=1e-4)


def test_conserva_las_proporciones_aplicando_una_sola_ganancia() -> None:
    original = _seno(0.1, 1.0) + _ruido(0.0004, 1.0)

    resultado = normalizar(original)

    ganancia = resultado / np.where(original == 0, 1, original)
    mascara = np.abs(original) > 0.01
    assert float(ganancia[mascara].std()) < 1e-3


def test_no_amplifica_ruido_de_fondo_sin_voz() -> None:
    resultado = normalizar(_ruido(0.0004, 2.0))

    assert resultado.size == 0
    assert resultado.dtype == np.float32


def test_la_ganancia_tiene_un_tope() -> None:
    # Voz apenas por encima del umbral: no se amplifica más allá del tope.
    original = _seno(0.005, 1.0)
    assert tiene_voz(original)

    resultado = normalizar(original)

    assert float(np.abs(resultado).max()) == pytest.approx(0.005 * GANANCIA_MAXIMA, rel=1e-3)


@pytest.mark.parametrize("segundos", [0.1, 0.4, DURACION_MINIMA_S - 0.01])
def test_un_audio_de_menos_de_medio_segundo_se_descarta(segundos: float) -> None:
    assert normalizar(_seno(0.2, segundos)).size == 0


def test_medio_segundo_justo_se_conserva() -> None:
    assert normalizar(_seno(0.2, DURACION_MINIMA_S)).size == int(DURACION_MINIMA_S * FRECUENCIA)


def test_silencio_y_audio_vacio_devuelven_audio_vacio() -> None:
    assert normalizar(np.zeros(FRECUENCIA * 2, dtype=np.float32)).size == 0
    assert normalizar(np.zeros(0, dtype=np.int16)).size == 0


# ---- propiedades -------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    hnp.arrays(
        dtype=np.float32,
        shape=st.integers(0, 20000),
        elements=st.floats(-1.0, 1.0, width=32, allow_nan=False),
    )
)
def test_el_resultado_es_vacio_o_tiene_exactamente_el_pico_objetivo(audio: np.ndarray) -> None:
    resultado = normalizar(audio)

    assert resultado.dtype == np.float32
    assert np.isfinite(resultado).all()
    if resultado.size:
        pico_entrada = float(np.abs(audio).max())
        pico_salida = float(np.abs(resultado).max())
        ganancia = pico_salida / pico_entrada
        assert ganancia <= GANANCIA_MAXIMA * (1 + 1e-3)
        # O llegó al pico objetivo, o se topó con la ganancia máxima.
        assert pico_salida == pytest.approx(PICO_OBJETIVO, abs=1e-4) or ganancia == pytest.approx(
            GANANCIA_MAXIMA, rel=1e-3
        )
