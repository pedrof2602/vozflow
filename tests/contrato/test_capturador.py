"""Contrato del capturador de audio, con un doble de ``sounddevice`` (sin micrófono)."""

import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from vozflow.audio.captura import (
    Capturador,
    Dispositivo,
    ErrorDeAudio,
    listar_dispositivos,
    nivel_de_bloque,
)
from vozflow.audio.senal import FRECUENCIA


class ErrorDePortAudio(Exception):
    """Hace de ``sounddevice.PortAudioError`` en el doble."""


class FalsoFlujo:
    def __init__(self, **argumentos: Any) -> None:
        self.argumentos = argumentos
        self.callback: Callable[..., None] = argumentos["callback"]
        self.iniciado = False
        self.detenido = False
        self.cerrado = False

    def start(self) -> None:
        self.iniciado = True

    def stop(self) -> None:
        self.detenido = True

    def close(self) -> None:
        self.cerrado = True

    def entregar(self, bloque: np.ndarray, estado: object | None = None) -> None:
        """Simula que PortAudio entrega un bloque de audio."""
        self.callback(bloque, len(bloque), None, estado or SimpleNamespace(input_overflow=False))


class FalsoSD:
    PortAudioError = ErrorDePortAudio

    def __init__(
        self,
        dispositivos: list[dict[str, Any]] | None = None,
        predeterminado: int | None = None,
        falla_al_abrir: bool = False,
        falla_al_iniciar: bool = False,
    ) -> None:
        self.dispositivos = dispositivos or []
        self.predeterminado = predeterminado
        self.falla_al_abrir = falla_al_abrir
        self.falla_al_iniciar = falla_al_iniciar
        self.flujos: list[FalsoFlujo] = []

    def InputStream(self, **argumentos: Any) -> FalsoFlujo:  # noqa: N802 - imita sounddevice
        if self.falla_al_abrir:
            raise ErrorDePortAudio("Error opening InputStream: Invalid device")
        flujo = FalsoFlujo(**argumentos)
        if self.falla_al_iniciar:
            flujo.start = self._fallar  # type: ignore[method-assign]
        self.flujos.append(flujo)
        return flujo

    @staticmethod
    def _fallar() -> None:
        raise ErrorDePortAudio("Error starting stream")

    def query_devices(self, device: Any = None, kind: str | None = None) -> Any:
        if kind == "input":
            if self.predeterminado is None:
                raise ErrorDePortAudio("No default input device")
            return self.dispositivos[self.predeterminado]
        return self.dispositivos


def _voz(segundos: float, amplitud: int = 8000) -> np.ndarray:
    t = np.arange(int(segundos * FRECUENCIA)) / FRECUENCIA
    onda = (amplitud * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    return onda.reshape(-1, 1)  # PortAudio entrega (cuadros, canales)


def _entregar_en_bloques(flujo: FalsoFlujo, audio: np.ndarray, bloque: int = 1600) -> None:
    for inicio in range(0, len(audio), bloque):
        flujo.entregar(audio[inicio : inicio + bloque].copy())


# ---- abrir el flujo -----------------------------------------------------------


def test_iniciar_abre_un_flujo_de_16_khz_mono_de_16_bits_y_lo_arranca() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)

    capturador.iniciar()

    flujo = sd.flujos[0]
    assert flujo.argumentos["samplerate"] == FRECUENCIA
    assert flujo.argumentos["channels"] == 1
    assert flujo.argumentos["dtype"] == "int16"
    assert flujo.argumentos["device"] is None
    assert callable(flujo.argumentos["callback"])
    assert flujo.iniciado is True
    assert capturador.grabando is True


@pytest.mark.parametrize("dispositivo", ["Micrófono USB", 3])
def test_iniciar_pasa_el_dispositivo_elegido(dispositivo: str | int) -> None:
    sd = FalsoSD()

    Capturador(sd=sd).iniciar(dispositivo)

    assert sd.flujos[0].argumentos["device"] == dispositivo


def test_no_se_puede_iniciar_dos_veces() -> None:
    capturador = Capturador(sd=FalsoSD())
    capturador.iniciar()

    with pytest.raises(RuntimeError, match="ya está"):
        capturador.iniciar()


@pytest.mark.parametrize(("al_abrir", "al_iniciar"), [(True, False), (False, True)])
def test_un_error_del_microfono_se_informa_con_un_mensaje_claro(
    al_abrir: bool, al_iniciar: bool
) -> None:
    sd = FalsoSD(falla_al_abrir=al_abrir, falla_al_iniciar=al_iniciar)
    capturador = Capturador(sd=sd)

    with pytest.raises(ErrorDeAudio, match="micrófono"):
        capturador.iniciar()

    assert capturador.grabando is False
    assert all(flujo.cerrado for flujo in sd.flujos)  # no queda un flujo abierto


# ---- detener ------------------------------------------------------------------


def test_detener_devuelve_el_audio_normalizado_y_cierra_el_flujo() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    _entregar_en_bloques(sd.flujos[0], _voz(1.0))

    audio = capturador.detener()

    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert audio.size == FRECUENCIA
    assert float(np.abs(audio).max()) == pytest.approx(0.9, abs=1e-3)
    assert sd.flujos[0].detenido and sd.flujos[0].cerrado
    assert capturador.grabando is False


def test_un_audio_de_menos_de_medio_segundo_se_devuelve_vacio() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    _entregar_en_bloques(sd.flujos[0], _voz(0.3))

    assert capturador.detener().size == 0


def test_detener_sin_haber_iniciado_devuelve_audio_vacio_sin_error() -> None:
    assert Capturador(sd=FalsoSD()).detener().size == 0


def test_se_puede_grabar_de_nuevo_y_no_arrastra_audio_anterior() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    _entregar_en_bloques(sd.flujos[0], _voz(1.0))
    capturador.detener()

    capturador.iniciar()
    _entregar_en_bloques(sd.flujos[1], _voz(0.6))
    audio = capturador.detener()

    assert audio.size == int(0.6 * FRECUENCIA)


def test_los_bloques_que_llegan_tras_detener_se_ignoran() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    _entregar_en_bloques(sd.flujos[0], _voz(1.0))
    capturador.detener()

    sd.flujos[0].entregar(_voz(0.5))  # llegada tardía del hilo de audio

    assert capturador.audio_acumulado().size == 0


def test_el_callback_copia_el_bloque_porque_portaudio_reutiliza_el_bufer() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    bloque = _voz(0.1)
    sd.flujos[0].entregar(bloque)

    bloque[:] = 0  # PortAudio vuelve a escribir sobre el mismo búfer

    assert int(np.abs(capturador.audio_acumulado()).max()) > 0


def test_audio_acumulado_permite_ver_la_grabacion_en_curso() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    _entregar_en_bloques(sd.flujos[0], _voz(0.5))
    primero = capturador.audio_acumulado().size
    _entregar_en_bloques(sd.flujos[0], _voz(0.5))

    assert primero == int(0.5 * FRECUENCIA)
    assert capturador.audio_acumulado().size == FRECUENCIA
    assert capturador.grabando is True


def test_una_grabacion_demasiado_larga_se_corta_en_el_maximo() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd, duracion_maxima_s=1.0)
    capturador.iniciar()

    _entregar_en_bloques(sd.flujos[0], _voz(2.0))

    assert capturador.detener().size == FRECUENCIA
    assert capturador.truncado is True


def test_un_desbordamiento_de_entrada_se_registra_sin_interrumpir(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()

    with caplog.at_level(logging.WARNING):
        sd.flujos[0].entregar(_voz(0.1), SimpleNamespace(input_overflow=True))

    assert "desbordamiento" in caplog.text
    assert capturador.audio_acumulado().size == int(0.1 * FRECUENCIA)


# ---- nivel para el indicador ----------------------------------------------------


def test_el_nivel_empieza_en_cero_y_sigue_a_la_voz() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    assert capturador.nivel == 0.0

    sd.flujos[0].entregar(_voz(0.1, amplitud=12000))
    fuerte = capturador.nivel
    sd.flujos[0].entregar(np.zeros((1600, 1), dtype=np.int16))
    silencio = capturador.nivel

    assert 0.5 < fuerte <= 1.0
    assert 0.0 <= silencio < 0.05


def test_el_callback_de_nivel_recibe_el_valor_de_cada_bloque() -> None:
    recibidos: list[float] = []
    sd = FalsoSD()
    capturador = Capturador(sd=sd, al_nivel=recibidos.append)
    capturador.iniciar()

    _entregar_en_bloques(sd.flujos[0], _voz(0.3))

    assert len(recibidos) == 3
    assert all(0.0 <= nivel <= 1.0 for nivel in recibidos)


def test_el_nivel_vuelve_a_cero_al_detener() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    sd.flujos[0].entregar(_voz(0.1, amplitud=12000))

    capturador.detener()

    assert capturador.nivel == 0.0


@settings(max_examples=200, deadline=None)
@given(hnp.arrays(dtype=np.int16, shape=st.integers(0, 4000)))
def test_el_nivel_de_cualquier_bloque_esta_entre_cero_y_uno(bloque: np.ndarray) -> None:
    assert 0.0 <= nivel_de_bloque(bloque) <= 1.0


# ---- listar dispositivos (RF-005) --------------------------------------------------

_DISPOSITIVOS: list[dict[str, Any]] = [
    {"name": "HDMI 0", "index": 0, "max_input_channels": 0},
    {"name": "Micrófono interno", "index": 1, "max_input_channels": 2},
    {"name": "Cámara web", "index": 2, "max_input_channels": 1},
]


def test_lista_solo_los_dispositivos_con_entrada_y_marca_el_predeterminado() -> None:
    sd = FalsoSD(dispositivos=_DISPOSITIVOS, predeterminado=1)

    assert listar_dispositivos(sd=sd) == [
        Dispositivo(
            indice=1, nombre="Micrófono interno", canales_de_entrada=2, es_predeterminado=True
        ),
        Dispositivo(indice=2, nombre="Cámara web", canales_de_entrada=1, es_predeterminado=False),
    ]


def test_sin_dispositivo_predeterminado_ninguno_se_marca() -> None:
    sd = FalsoSD(dispositivos=_DISPOSITIVOS, predeterminado=None)

    assert not any(d.es_predeterminado for d in listar_dispositivos(sd=sd))


def test_sin_dispositivos_la_lista_esta_vacia() -> None:
    assert listar_dispositivos(sd=FalsoSD()) == []


# ---- audio sin normalizar (para transcribir por tramos) ------------------------------


def test_detener_crudo_devuelve_las_muestras_originales_sin_normalizar() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    original = _voz(1.0, amplitud=3000)
    _entregar_en_bloques(sd.flujos[0], original)

    crudo = capturador.detener_crudo()

    assert crudo.dtype == np.int16
    np.testing.assert_array_equal(crudo, original[:, 0])
    assert capturador.grabando is False
    assert sd.flujos[0].detenido and sd.flujos[0].cerrado


def test_detener_crudo_no_descarta_el_audio_corto_ni_el_silencio() -> None:
    sd = FalsoSD()
    capturador = Capturador(sd=sd)
    capturador.iniciar()
    sd.flujos[0].entregar(np.zeros((800, 1), dtype=np.int16))

    assert capturador.detener_crudo().size == 800


def test_detener_crudo_sin_haber_iniciado_devuelve_vacio() -> None:
    crudo = Capturador(sd=FalsoSD()).detener_crudo()

    assert crudo.dtype == np.int16
    assert crudo.size == 0
