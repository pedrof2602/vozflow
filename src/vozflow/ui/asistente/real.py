"""El medidor de nivel y el probador de voz de verdad del asistente (002).

Los dos usan su propia captura de audio y el motor que ya está cargado para dictar; nada de lo que
pasa por acá se guarda ni se pega.
"""

import logging
import threading
from collections.abc import Callable

from vozflow.aplicacion import Grabadora, dictar_hasta
from vozflow.audio.captura import ErrorDeAudio
from vozflow.transcripcion.motor import MotorDeTranscripcion

_registro = logging.getLogger(__name__)
_ESPERA_PARA_EMPEZAR_S = 5.0
_ESPERA_PARA_TERMINAR_S = 60.0


class MedidorReal:
    """Abre el micrófono solo para leer su volumen; el audio se descarta."""

    def __init__(self, crear_grabadora: Callable[[], Grabadora]) -> None:
        self._crear = crear_grabadora
        self._grabadora: Grabadora | None = None

    def iniciar(self, dispositivo: str | int | None) -> None:
        grabadora = self._crear()
        grabadora.iniciar(dispositivo)
        self._grabadora = grabadora

    def nivel(self) -> float:
        if self._grabadora is None:
            return 0.0
        return float(getattr(self._grabadora, "nivel", 0.0))

    def detener(self) -> None:
        grabadora, self._grabadora = self._grabadora, None
        if grabadora is not None:
            grabadora.detener_crudo()  # se tira: este audio no se usa para nada


class ProbadorReal:
    def __init__(
        self,
        *,
        motor: MotorDeTranscripcion,
        crear_grabadora: Callable[[], Grabadora],
        dispositivo: Callable[[], str | int | None],
        idioma: Callable[[], str | None],
        modelo_disponible: Callable[[], bool],
        descargar: Callable[[Callable[[int, int], None]], str],
    ) -> None:
        self._motor = motor
        self._crear_grabadora = crear_grabadora
        self._dispositivo = dispositivo
        self._idioma = idioma
        self._modelo_disponible = modelo_disponible
        self._descargar = descargar
        self._parar = threading.Event()
        self._listo = threading.Event()
        self._fin = threading.Event()
        self._texto: str | None = None
        self._error: BaseException | None = None
        self._cancelado = False

    def modelo_descargado(self) -> bool:
        return self._modelo_disponible()

    def descargar_modelo(
        self,
        al_avance: Callable[[int, int], None],
        al_listo: Callable[[], None],
        al_error: Callable[[str], None],
    ) -> None:
        def correr() -> None:
            try:
                self._descargar(al_avance)
            except Exception as error:
                _registro.warning("No se pudo descargar el modelo desde el asistente: %s", error)
                al_error(type(error).__name__)
                return
            al_listo()

        threading.Thread(target=correr, name="vozflow-asistente-descarga", daemon=True).start()

    def preparar(self, al_listo: Callable[[], None], al_error: Callable[[str], None]) -> None:
        def correr() -> None:
            try:
                self._motor.cargar()  # si ya estaba cargado, vuelve enseguida
            except Exception as error:
                _registro.warning("No se pudo preparar el modelo en el asistente: %s", error)
                al_error(type(error).__name__)
                return
            al_listo()

        threading.Thread(target=correr, name="vozflow-asistente-modelo", daemon=True).start()

    def empezar(self) -> None:
        """Abre el micrófono; si no se puede, lo lanza acá mismo (``ErrorDeAudio``)."""
        self._parar = threading.Event()
        self._listo = threading.Event()
        self._fin = threading.Event()
        self._texto = None
        self._error = None
        self._cancelado = False
        threading.Thread(target=self._correr, name="vozflow-asistente-prueba", daemon=True).start()
        self._listo.wait(_ESPERA_PARA_EMPEZAR_S)
        if self._error is not None:
            raise self._error

    def terminar(
        self, al_resultado: Callable[[str], None], al_error: Callable[[str], None]
    ) -> None:
        self._parar.set()

        def entregar() -> None:
            self._fin.wait(_ESPERA_PARA_TERMINAR_S)
            if self._cancelado:
                return
            if self._error is not None or self._texto is None:
                al_error(type(self._error).__name__ if self._error else "SinResultado")
                return
            al_resultado(self._texto)

        threading.Thread(target=entregar, name="vozflow-asistente-entrega", daemon=True).start()

    def cancelar(self) -> None:
        self._cancelado = True
        self._parar.set()
        self._fin.wait(_ESPERA_PARA_EMPEZAR_S)

    def _correr(self) -> None:
        try:
            resultado = dictar_hasta(
                grabadora=self._crear_grabadora(),
                motor=self._motor,
                seguir=lambda: not self._parar.is_set(),
                dispositivo=self._dispositivo(),
                idioma=self._idioma(),
                al_empezar=self._listo.set,
            )
            self._texto = resultado.procesado.texto
        except BaseException as error:
            if not isinstance(error, ErrorDeAudio):
                _registro.warning("Falló la prueba de voz del asistente: %s", error)
            self._error = error
            self._listo.set()
        finally:
            self._fin.set()
