import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.audio.senal import FRECUENCIA, TRAMA, UMBRAL_RMS, nivel_eficaz_por_trama
from vozflow.audio.tramos import SILENCIO_MINIMO_S, TRAMO_MINIMO_S, cortar_por_silencio


def _voz(segundos: float) -> np.ndarray:
    t = np.arange(int(segundos * FRECUENCIA)) / FRECUENCIA
    return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _silencio(segundos: float) -> np.ndarray:
    return np.zeros(int(segundos * FRECUENCIA), dtype=np.float32)


def _armar(*partes: np.ndarray) -> np.ndarray:
    return np.concatenate(partes) if partes else np.zeros(0, dtype=np.float32)


def _esta_en_silencio(audio: np.ndarray, corte: int) -> bool:
    return bool(np.all(audio[corte : corte + TRAMA] == 0))


# ---- cortes entre frases ------------------------------------------------------


def test_corta_en_el_medio_de_cada_silencio_largo() -> None:
    audio = _armar(_voz(2.0), _silencio(1.0), _voz(2.0), _silencio(1.2), _voz(1.5))

    tramos = cortar_por_silencio(audio)

    assert len(tramos) == 3
    cortes = [fin for _, fin in tramos[:-1]]
    for corte in cortes:
        assert _esta_en_silencio(audio, corte)
    # El primer corte cae dentro del primer silencio, el segundo dentro del segundo.
    assert 2.0 * FRECUENCIA < cortes[0] < 3.0 * FRECUENCIA
    assert 5.0 * FRECUENCIA < cortes[1] < 6.2 * FRECUENCIA


def test_los_tramos_cubren_todo_el_audio_sin_huecos_ni_solapes() -> None:
    audio = _armar(_voz(2.0), _silencio(1.0), _voz(2.0), _silencio(1.2), _voz(1.5))

    tramos = cortar_por_silencio(audio)

    assert tramos[0][0] == 0
    assert tramos[-1][1] == len(audio)
    for (_, fin), (inicio, _) in zip(tramos, tramos[1:], strict=False):
        assert fin == inicio


def test_la_voz_continua_no_se_corta() -> None:
    audio = _voz(5.0)

    assert cortar_por_silencio(audio) == [(0, len(audio))]


def test_una_pausa_corta_entre_palabras_no_corta() -> None:
    audio = _armar(_voz(2.0), _silencio(0.5), _voz(2.0))

    assert len(cortar_por_silencio(audio)) == 1


def test_el_silencio_minimo_para_cortar_es_de_0_8_segundos() -> None:
    assert SILENCIO_MINIMO_S == 0.8
    sin_corte = _armar(_voz(2.0), _silencio(0.76), _voz(2.0))
    con_corte = _armar(_voz(2.0), _silencio(0.86), _voz(2.0))

    assert len(cortar_por_silencio(sin_corte)) == 1
    assert len(cortar_por_silencio(con_corte)) == 2


# ---- tramos mínimos ---------------------------------------------------------------


def test_un_tramo_inicial_de_menos_de_un_segundo_se_une_al_siguiente() -> None:
    assert TRAMO_MINIMO_S == 1.0
    audio = _armar(_voz(0.4), _silencio(1.0), _voz(3.0))

    assert len(cortar_por_silencio(audio)) == 1


def test_un_tramo_final_de_menos_de_un_segundo_se_une_al_anterior() -> None:
    audio = _armar(_voz(3.0), _silencio(1.0), _voz(0.4))

    assert len(cortar_por_silencio(audio)) == 1


def test_un_tramo_justo_por_encima_del_minimo_se_conserva() -> None:
    audio = _armar(_voz(1.2), _silencio(1.0), _voz(3.0))

    assert len(cortar_por_silencio(audio)) == 2


# ---- bordes ---------------------------------------------------------------------------


def test_el_silencio_del_principio_y_del_final_no_genera_cortes() -> None:
    audio = _armar(_silencio(2.0), _voz(2.0), _silencio(2.0))

    assert cortar_por_silencio(audio) == [(0, len(audio))]


def test_audio_vacio_no_tiene_tramos() -> None:
    assert cortar_por_silencio(np.zeros(0, dtype=np.float32)) == []


def test_audio_todo_silencio_es_un_solo_tramo() -> None:
    audio = _silencio(3.0)

    assert cortar_por_silencio(audio) == [(0, len(audio))]


def test_un_audio_con_resto_de_muestras_no_pierde_el_final() -> None:
    audio = _armar(_voz(2.0), _silencio(1.0), _voz(2.0))[:-37]

    assert cortar_por_silencio(audio)[-1][1] == len(audio)


# ---- propiedades --------------------------------------------------------------------

_PARTE = st.tuples(st.booleans(), st.floats(0.1, 3.0))


@settings(max_examples=150, deadline=None)
@given(st.lists(_PARTE, max_size=8))
def test_propiedades_de_cualquier_secuencia_de_voz_y_silencio(
    partes: list[tuple[bool, float]],
) -> None:
    audio = _armar(*[_voz(d) if hay_voz else _silencio(d) for hay_voz, d in partes])

    tramos = cortar_por_silencio(audio)

    if len(audio) == 0:
        assert tramos == []
        return
    # Cubren todo, en orden, sin huecos.
    assert tramos[0][0] == 0 and tramos[-1][1] == len(audio)
    assert all(a[1] == b[0] for a, b in zip(tramos, tramos[1:], strict=False))
    # Ningún tramo es corto, salvo que todo el audio lo sea.
    assert len(tramos) == 1 or all(
        fin - inicio >= TRAMO_MINIMO_S * FRECUENCIA for inicio, fin in tramos
    )
    # Cada corte cae dentro de un silencio: nunca parte una palabra.
    niveles = nivel_eficaz_por_trama(audio)
    for _, corte in tramos[:-1]:
        assert corte % TRAMA == 0
        assert niveles[corte // TRAMA] < UMBRAL_RMS
