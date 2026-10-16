"""Dictado largo por tramos: se transcribe mientras la persona sigue hablando.

El motor tarda lo mismo en transcribir 5 s que 25 s (procesa una ventana fija de 30 s), así
que en un dictado largo conviene ir mandando al motor cada tramo que se cierra por un silencio.
Al soltar la tecla solo queda por transcribir el último, y la espera no crece con el largo del
dictado (research.md, sección 1).
"""

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait

import numpy as np
import numpy.typing as npt

from vozflow.audio.captura import a_float32, normalizar
from vozflow.audio.tramos import cortar_por_silencio
from vozflow.transcripcion.motor import MotorDeTranscripcion, Transcripcion

_Crudo = npt.NDArray[np.int16]
_Pendiente = tuple[int, "Future[Transcripcion | None]"]


class TranscriptorPorTramos:
    """Transcribe los tramos cerrados en un hilo aparte y une el resultado en orden.

    Uso: durante la grabación, llamar a ``actualizar`` cada tanto con todo el audio grabado
    hasta ahora; al soltar la tecla, llamar a ``terminar`` con el audio completo.
    """

    def __init__(self, motor: MotorDeTranscripcion, idioma: str | None, pista: str | None) -> None:
        self._motor = motor
        self._idioma = idioma
        self._pista = pista
        self._ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vozflow-tramos")
        self._candado = threading.Lock()
        self._pendientes: list[_Pendiente] = []
        self._enviado_hasta = 0
        self._terminado = False

    def actualizar(self, crudo: _Crudo) -> None:
        """Manda al motor los tramos que ya se cerraron con un silencio largo."""
        with self._candado:
            if self._terminado:
                return
            self._enviar_tramos_cerrados(crudo)

    def esperar_envios(self) -> None:
        """Espera a que el motor termine lo enviado hasta ahora (sin lanzar errores)."""
        with self._candado:
            futuros = [futuro for _, futuro in self._pendientes]
        wait(futuros)

    def terminar(self, crudo: _Crudo) -> Transcripcion:
        """Transcribe lo que falta y devuelve el texto completo, en orden.

        ``duracion_ms`` es lo que se esperó desde que se llamó a este método: la espera que
        siente la persona tras soltar la tecla.
        """
        inicio = time.perf_counter()
        with self._candado:
            if self._terminado:
                raise RuntimeError("El transcriptor ya terminó")
            self._terminado = True
            self._enviar_tramos_cerrados(crudo)
            resto = crudo[self._enviado_hasta :]
            if len(resto) > 0:
                self._enviar(resto)
            pendientes = list(self._pendientes)
        try:
            resultados = [(muestras, futuro.result()) for muestras, futuro in pendientes]
        finally:
            self._ejecutor.shutdown(wait=True, cancel_futures=True)
        milisegundos = round((time.perf_counter() - inicio) * 1000)
        return self._unir(resultados, milisegundos)

    def cancelar(self, esperar: bool = True) -> None:
        """Descarta lo pendiente. ``esperar=False`` no bloquea esperando el tramo en curso."""
        with self._candado:
            self._terminado = True
        self._ejecutor.shutdown(wait=esperar, cancel_futures=True)

    # ---- internos -------------------------------------------------------------------

    def _enviar_tramos_cerrados(self, crudo: _Crudo) -> None:
        resto = crudo[self._enviado_hasta :]
        if len(resto) == 0:
            return
        tramos = cortar_por_silencio(a_float32(resto))
        for inicio, fin in tramos[:-1]:  # el último puede seguir abierto
            self._enviar(resto[inicio:fin])
        if len(tramos) > 1:
            self._enviado_hasta += tramos[-1][0]

    def _enviar(self, tramo: _Crudo) -> None:
        copia = tramo.copy()
        self._pendientes.append((len(copia), self._ejecutor.submit(self._transcribir, copia)))

    def _transcribir(self, tramo: _Crudo) -> Transcripcion | None:
        audio = normalizar(tramo)
        if audio.size == 0:  # sin voz o demasiado corto
            return None
        return self._motor.transcribir(audio, self._pista, self._idioma)

    @staticmethod
    def _unir(
        resultados: list[tuple[int, Transcripcion | None]], milisegundos: int
    ) -> Transcripcion:
        con_texto = [(muestras, r) for muestras, r in resultados if r is not None]
        if not con_texto:
            return Transcripcion(
                texto="", idioma="", probabilidad_idioma=0.0, duracion_ms=milisegundos
            )
        # El idioma lo marca el tramo más largo.
        _, principal = max(con_texto, key=lambda par: par[0])
        texto = " ".join(r.texto for _, r in con_texto if r.texto)
        total = sum(muestras for muestras, _ in con_texto)
        return Transcripcion(
            texto=texto,
            idioma=principal.idioma,
            probabilidad_idioma=principal.probabilidad_idioma,
            duracion_ms=milisegundos,
            no_voz_probabilidad=max(r.no_voz_probabilidad for _, r in con_texto),
            logprob_medio=sum(r.logprob_medio * muestras for muestras, r in con_texto) / total,
        )
