"""Dictado largo por tramos: se transcribe mientras la persona sigue hablando."""

import threading
from dataclasses import dataclass, field

import numpy as np
import pytest

from vozflow.audio.senal import FRECUENCIA
from vozflow.transcripcion.motor import ErrorDeTranscripcion, Transcripcion
from vozflow.transcripcion.por_tramos import TranscriptorPorTramos


def _voz(segundos: float, amplitud: int = 6000) -> np.ndarray:
    t = np.arange(int(segundos * FRECUENCIA)) / FRECUENCIA
    return (amplitud * np.sin(2 * np.pi * 220 * t)).astype(np.int16)


def _silencio(segundos: float) -> np.ndarray:
    return np.zeros(int(segundos * FRECUENCIA), dtype=np.int16)


def _juntar(*partes: np.ndarray) -> np.ndarray:
    return np.concatenate(partes)


@dataclass
class Llamada:
    muestras: int
    pico: float
    pista: str | None
    idioma: str | None
    hilo: str


@dataclass
class MotorQueEnumera:
    """Devuelve «tramo1», «tramo2»… y registra desde qué hilo y con qué lo llamaron."""

    idiomas: list[str] = field(default_factory=lambda: ["es"])
    no_voz: list[float] = field(default_factory=lambda: [0.1])
    logprob: list[float] = field(default_factory=lambda: [-0.3])
    llamadas: list[Llamada] = field(default_factory=list)
    primera_llamada: threading.Event = field(default_factory=threading.Event)
    liberar: threading.Event | None = None
    falla_en: int | None = None

    def cargar(self) -> None: ...

    def descargar(self) -> None: ...

    def transcribir(
        self, audio: np.ndarray, pista: str | None, idioma: str | None
    ) -> Transcripcion:
        self.llamadas.append(
            Llamada(
                muestras=len(audio),
                pico=float(np.abs(audio).max()),
                pista=pista,
                idioma=idioma,
                hilo=threading.current_thread().name,
            )
        )
        numero = len(self.llamadas)
        self.primera_llamada.set()
        if self.liberar is not None and numero == 1:
            assert self.liberar.wait(timeout=5), "la prueba no liberó el primer tramo"
        if self.falla_en == numero:
            raise ErrorDeTranscripcion("falló el motor")
        lenguaje = self.idiomas[(numero - 1) % len(self.idiomas)]
        return Transcripcion(
            texto=f"tramo{numero}",
            idioma=lenguaje,
            probabilidad_idioma=0.9,
            duracion_ms=5,
            no_voz_probabilidad=self.no_voz[(numero - 1) % len(self.no_voz)],
            logprob_medio=self.logprob[(numero - 1) % len(self.logprob)],
        )


DOS_FRASES = _juntar(_voz(2.0), _silencio(1.0), _voz(2.0))


# ---- se envía lo ya cerrado mientras se graba ----------------------


def test_un_tramo_cerrado_se_transcribe_en_otro_hilo_antes_de_soltar() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)

    transcriptor.actualizar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))
    assert motor.primera_llamada.wait(timeout=5)

    assert len(motor.llamadas) == 1
    assert motor.llamadas[0].hilo != threading.current_thread().name
    transcriptor.terminar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))


def test_mientras_no_haya_un_silencio_largo_no_se_envia_nada() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)

    transcriptor.actualizar(_voz(3.0))
    transcriptor.esperar_envios()

    assert motor.llamadas == []
    transcriptor.terminar(_voz(3.0))


def test_actualizar_varias_veces_con_el_mismo_audio_no_reenvia_el_tramo() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    audio = _juntar(_voz(2.0), _silencio(1.0), _voz(0.5))

    for _ in range(4):
        transcriptor.actualizar(audio)
        transcriptor.esperar_envios()

    assert len(motor.llamadas) == 1
    transcriptor.terminar(audio)


# ---- al soltar solo queda el último ----------------------


def test_al_terminar_solo_se_transcribe_lo_que_falta_y_se_une_en_orden() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    transcriptor.actualizar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))
    transcriptor.esperar_envios()

    resultado = transcriptor.terminar(DOS_FRASES)

    assert len(motor.llamadas) == 2  # un tramo cerrado + el último
    assert resultado.texto == "tramo1 tramo2"


def test_sin_tramos_cerrados_se_transcribe_todo_de_una_vez_al_terminar() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)

    resultado = transcriptor.terminar(_voz(3.0))

    assert len(motor.llamadas) == 1
    assert resultado.texto == "tramo1"


def test_los_tramos_cubren_todo_el_audio_sin_perder_muestras() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    audio = _juntar(_voz(2.0), _silencio(1.0), _voz(2.0), _silencio(1.2), _voz(1.5))
    transcriptor.actualizar(audio[: 7 * FRECUENCIA])
    transcriptor.esperar_envios()

    transcriptor.terminar(audio)

    assert sum(llamada.muestras for llamada in motor.llamadas) == len(audio)


def test_el_resultado_sale_en_orden_aunque_el_primer_tramo_tarde_mas() -> None:
    liberar = threading.Event()
    motor = MotorQueEnumera(liberar=liberar)
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    transcriptor.actualizar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))
    assert motor.primera_llamada.wait(timeout=5)

    liberar.set()
    resultado = transcriptor.terminar(DOS_FRASES)

    assert resultado.texto == "tramo1 tramo2"


# ---- parámetros y normalización ----------------------


def test_cada_tramo_lleva_la_pista_el_idioma_y_llega_normalizado() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma="es", pista="SQLAlchemy")

    transcriptor.terminar(DOS_FRASES)

    assert motor.llamadas, "debería haber transcrito algo"
    for llamada in motor.llamadas:
        assert llamada.pista == "SQLAlchemy"
        assert llamada.idioma == "es"
        assert llamada.pico == pytest.approx(0.9, abs=1e-3)


def test_el_idioma_final_es_el_del_tramo_mas_largo() -> None:
    motor = MotorQueEnumera(idiomas=["en", "es"])
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    audio = _juntar(_voz(1.5), _silencio(1.0), _voz(4.0))  # el segundo tramo es más largo

    resultado = transcriptor.terminar(audio)

    assert resultado.idioma == "es"


# ---- bordes y errores ----------------------


def test_un_audio_sin_voz_da_texto_vacio_sin_llamar_al_motor() -> None:
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)

    resultado = transcriptor.terminar(_silencio(2.0))

    assert resultado.texto == ""
    assert motor.llamadas == []


def test_un_audio_vacio_da_texto_vacio() -> None:
    transcriptor = TranscriptorPorTramos(MotorQueEnumera(), idioma=None, pista=None)

    assert transcriptor.terminar(np.zeros(0, dtype=np.int16)).texto == ""


def test_un_error_del_motor_en_un_tramo_se_informa_al_terminar() -> None:
    motor = MotorQueEnumera(falla_en=1)
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    transcriptor.actualizar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))

    with pytest.raises(ErrorDeTranscripcion, match="falló"):
        transcriptor.terminar(DOS_FRASES)


def test_no_se_puede_terminar_dos_veces() -> None:
    transcriptor = TranscriptorPorTramos(MotorQueEnumera(), idioma=None, pista=None)
    transcriptor.terminar(_voz(1.0))

    with pytest.raises(RuntimeError, match="ya terminó"):
        transcriptor.terminar(_voz(1.0))


def test_terminar_no_deja_hilos_colgados() -> None:
    antes = threading.active_count()
    transcriptor = TranscriptorPorTramos(MotorQueEnumera(), idioma=None, pista=None)
    transcriptor.actualizar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))
    transcriptor.terminar(DOS_FRASES)

    assert threading.active_count() == antes


def test_cancelar_descarta_lo_pendiente_y_libera_el_hilo() -> None:
    antes = threading.active_count()
    motor = MotorQueEnumera()
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    transcriptor.actualizar(_juntar(_voz(2.0), _silencio(1.0), _voz(0.5)))

    transcriptor.cancelar()

    assert threading.active_count() == antes
    with pytest.raises(RuntimeError, match="ya terminó"):
        transcriptor.terminar(DOS_FRASES)


def test_la_confianza_combinada_toma_la_peor_probabilidad_de_no_voz_y_pondera_el_logprob() -> None:
    motor = MotorQueEnumera(no_voz=[0.05, 0.50], logprob=[-0.2, -1.0])
    transcriptor = TranscriptorPorTramos(motor, idioma=None, pista=None)
    audio = _juntar(_voz(3.0), _silencio(1.0), _voz(1.0))  # tramos de ~3,5 s y ~1,5 s

    resultado = transcriptor.terminar(audio)

    assert resultado.no_voz_probabilidad == pytest.approx(0.50)
    primero, segundo = motor.llamadas[0].muestras, motor.llamadas[1].muestras
    esperado = (-0.2 * primero + -1.0 * segundo) / (primero + segundo)
    assert resultado.logprob_medio == pytest.approx(esperado)
