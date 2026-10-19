"""El medidor y el probador de verdad del asistente, con dobles del micrófono y del motor (002)."""

import threading
import time

import pytest

from tests.dobles import GrabadoraFalsa, MotorFalso
from vozflow.audio.captura import ErrorDeAudio
from vozflow.transcripcion.motor import ErrorDeTranscripcion
from vozflow.ui.asistente.real import MedidorReal, ProbadorReal


class GrabadoraConNivel(GrabadoraFalsa):
    nivel = 0.0


def _esperar(evento: threading.Event, segundos: float = 3.0) -> bool:
    return evento.wait(segundos)


# ---- medidor ----------------------------------------------------------------------------------------------------


def test_el_medidor_abre_el_micrófono_pedido_y_lee_su_nivel() -> None:
    grabadora = GrabadoraConNivel()
    medidor = MedidorReal(lambda: grabadora)

    medidor.iniciar("Auriculares USB")
    grabadora.nivel = 0.6

    assert grabadora.iniciadas == 1 and medidor.nivel() == 0.6


def test_el_medidor_detiene_y_suelta_el_microfono() -> None:
    grabadora = GrabadoraConNivel()
    medidor = MedidorReal(lambda: grabadora)
    medidor.iniciar(None)

    medidor.detener()

    assert grabadora.detenidas == 1 and medidor.nivel() == 0.0


def test_el_medidor_sin_iniciar_da_cero_y_detener_no_falla() -> None:
    medidor = MedidorReal(lambda: GrabadoraConNivel())

    assert medidor.nivel() == 0.0
    medidor.detener()


def test_un_error_de_audio_al_iniciar_se_propaga() -> None:
    grabadora = GrabadoraConNivel()
    grabadora.fallar_al_iniciar = ErrorDeAudio("ocupado", "microfono_ocupado")
    medidor = MedidorReal(lambda: grabadora)

    with pytest.raises(ErrorDeAudio):
        medidor.iniciar(None)


def test_el_medidor_no_graba_ni_guarda_audio() -> None:
    grabadora = GrabadoraConNivel()
    medidor = MedidorReal(lambda: grabadora)
    medidor.iniciar(None)

    medidor.nivel()
    medidor.detener()

    assert not hasattr(medidor, "audio") and grabadora.detenidas == 1


# ---- probador ---------------------------------------------------------------------------------------------------


def _probador(
    motor: MotorFalso | None = None,
    grabadora: GrabadoraFalsa | None = None,
    descargado: bool = True,
    descarga: object = None,
) -> tuple[ProbadorReal, MotorFalso, GrabadoraFalsa]:
    motor = motor or MotorFalso(texto="hola mundo")
    grabadora = grabadora or GrabadoraFalsa(1.5)
    probador = ProbadorReal(
        motor=motor,
        crear_grabadora=lambda: grabadora,
        dispositivo=lambda: None,
        idioma=lambda: None,
        modelo_disponible=lambda: descargado,
        descargar=descarga or (lambda al_avance: "/modelo"),  # type: ignore[arg-type]
    )
    return probador, motor, grabadora


def test_preparar_carga_el_modelo_sin_bloquear_y_avisa() -> None:
    probador, motor, _ = _probador()
    listo = threading.Event()

    probador.preparar(listo.set, lambda m: None)

    assert _esperar(listo) and motor.cargado is True


def test_si_el_modelo_no_carga_lo_avisa_como_error() -> None:
    motor = MotorFalso()

    def falla() -> None:
        raise ErrorDeTranscripcion("no cargó")

    motor.cargar = falla  # type: ignore[method-assign]
    probador, _, _ = _probador(motor)
    error = threading.Event()

    probador.preparar(lambda: None, lambda mensaje: error.set())

    assert _esperar(error)


def test_grabar_y_terminar_devuelve_el_texto_limpio() -> None:
    probador, motor, grabadora = _probador()
    motor.cargar()
    texto: list[str] = []
    listo = threading.Event()

    def al_resultado(entendido: str) -> None:
        texto.append(entendido)
        listo.set()

    probador.empezar()
    probador.terminar(al_resultado, lambda m: listo.set())

    assert _esperar(listo) and texto == ["Hola mundo."]
    assert grabadora.iniciadas == 1 and grabadora.detenidas == 1


def test_un_error_del_microfono_al_empezar_se_lanza_en_el_momento() -> None:
    grabadora = GrabadoraFalsa()
    grabadora.fallar_al_iniciar = ErrorDeAudio("ocupado", "microfono_ocupado")
    probador, motor, _ = _probador(grabadora=grabadora)
    motor.cargar()

    with pytest.raises(ErrorDeAudio) as error:
        probador.empezar()

    assert error.value.codigo == "microfono_ocupado"


def test_cancelar_suelta_el_microfono_sin_entregar_resultado() -> None:
    probador, motor, grabadora = _probador()
    motor.cargar()
    probador.empezar()
    resultados: list[str] = []

    probador.cancelar()
    time.sleep(0.1)

    assert grabadora.detenidas == 1 and resultados == []


def test_si_la_transcripcion_falla_avisa_sin_detalles() -> None:
    probador, motor, _ = _probador()
    motor.cargar()

    def roto(audio, pista, idioma):  # type: ignore[no-untyped-def]
        raise ErrorDeTranscripcion("falló")

    motor.transcribir = roto  # type: ignore[method-assign]
    probador.empezar()
    error = threading.Event()

    probador.terminar(lambda t: None, lambda mensaje: error.set())

    assert _esperar(error)


def test_el_modelo_descargado_se_consulta_al_momento() -> None:
    assert _probador(descargado=False)[0].modelo_descargado() is False
    assert _probador(descargado=True)[0].modelo_descargado() is True


def test_descargar_pasa_el_avance_y_avisa_al_terminar() -> None:
    avances: list[tuple[int, int]] = []

    def descarga(al_avance) -> str:  # type: ignore[no-untyped-def]
        al_avance(10, 100)
        al_avance(100, 100)
        return "/modelo"

    probador, _, _ = _probador(descarga=descarga)
    listo = threading.Event()

    probador.descargar_modelo(lambda h, t: avances.append((h, t)), listo.set, lambda m: None)

    assert _esperar(listo) and avances == [(10, 100), (100, 100)]


def test_si_la_descarga_falla_avisa_como_error() -> None:
    def descarga(al_avance) -> str:  # type: ignore[no-untyped-def]
        raise ErrorDeTranscripcion("sin red", "modelo_faltante")

    probador, _, _ = _probador(descarga=descarga)
    error = threading.Event()

    probador.descargar_modelo(lambda h, t: None, lambda: None, lambda m: error.set())

    assert _esperar(error)
