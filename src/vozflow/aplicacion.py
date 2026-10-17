"""Une las piezas de vozflow: el dictado de la línea de comandos y la ``Aplicacion``."""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from concurrent.futures import TimeoutError as EsperaAgotada
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np
import numpy.typing as npt

from vozflow.atajos.puerto import AccionDeAtajo, EscuchaDeAtajos, EventoDeAtajo, FaseDeAtajo
from vozflow.audio.captura import ErrorDeAudio
from vozflow.audio.senal import FRECUENCIA
from vozflow.configuracion import ConfiguracionEstatica, FuenteDeConfiguracion
from vozflow.dominio.dictado import EstadoDelDictado, EstadoDictado, Evento
from vozflow.dominio.historial import EstadoDelHistorial
from vozflow.dominio.modos import Modo
from vozflow.dominio.tuberia import (
    OPCIONES_POR_DEFECTO,
    OpcionesDeTuberia,
    ResultadoProceso,
    completar,
    procesar,
)
from vozflow.insercion.puerto import Insertor
from vozflow.reescritura import ResultadoReescritura
from vozflow.transcripcion.motor import ErrorDeTranscripcion, MotorDeTranscripcion, Transcripcion
from vozflow.transcripcion.por_tramos import TranscriptorPorTramos
from vozflow.ventana.puerto import InfoVentana, VentanaActiva

_registro = logging.getLogger(__name__)

INTERVALO_DE_REVISION_S = 1.0
"""Cada cuánto se revisa el audio grabado para mandar al motor los tramos cerrados."""


class Grabadora(Protocol):
    """Lo que ``dictar_una_vez`` necesita de la captura; ``Capturador`` lo cumple."""

    def iniciar(self, dispositivo: str | int | None = None) -> None: ...

    def audio_acumulado(self) -> npt.NDArray[np.int16]: ...

    def detener_crudo(self) -> npt.NDArray[np.int16]: ...


@dataclass(frozen=True)
class ResultadoDictado:
    transcripcion: Transcripcion
    """Lo que devolvió el motor, sin tocar."""
    procesado: ResultadoProceso
    """Después de la tubería de texto: comandos de voz, limpieza y puntuación."""
    segundos_grabados: float
    espera_tras_soltar_ms: int
    """Lo que tardó en tener el texto una vez terminada la grabación."""
    audio: npt.NDArray[np.int16]
    """Lo grabado, sin normalizar."""


def _dictar(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    mientras_graba: Callable[[Callable[[], None]], None],
    dispositivo: str | int | None,
    idioma: str | None,
    pista: str | None,
    opciones: OpcionesDeTuberia,
    al_empezar: Callable[[], None] | None,
) -> ResultadoDictado:
    """Esqueleto común: cargar, grabar, transcribir por tramos y procesar el texto.

    ``mientras_graba`` decide cuándo terminar; recibe una función ``revisar`` que debe llamar
    cada tanto para que los tramos ya cerrados se manden al motor.
    """
    motor.cargar()
    transcriptor = TranscriptorPorTramos(motor, idioma=idioma, pista=pista)
    try:
        grabadora.iniciar(dispositivo)
    except BaseException:
        transcriptor.cancelar(esperar=False)
        raise
    if al_empezar is not None:
        al_empezar()
    try:
        mientras_graba(lambda: transcriptor.actualizar(grabadora.audio_acumulado()))
    except BaseException:
        grabadora.detener_crudo()
        transcriptor.cancelar(esperar=False)
        raise
    crudo = grabadora.detener_crudo()
    try:
        transcripcion = transcriptor.terminar(crudo)
    except BaseException:
        transcriptor.cancelar(esperar=False)
        raise
    procesado = procesar(transcripcion.texto, idioma or transcripcion.idioma or None, opciones)
    return ResultadoDictado(
        transcripcion=transcripcion,
        procesado=procesado,
        segundos_grabados=len(crudo) / FRECUENCIA,
        espera_tras_soltar_ms=transcripcion.duracion_ms,
        audio=crudo,
    )


def dictar_una_vez(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    segundos: float,
    dispositivo: str | int | None = None,
    idioma: str | None = None,
    pista: str | None = None,
    opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO,
    esperar: Callable[[float], None] = time.sleep,
    al_empezar: Callable[[], None] | None = None,
) -> ResultadoDictado:
    """Graba ``segundos``, transcribe (por tramos, mientras graba) y procesa el texto.

    El motor se carga *antes* de abrir el micrófono: así un modelo que falta o tarda en cargar
    se descubre sin haber grabado nada.
    """

    def esperar_el_tiempo(revisar: Callable[[], None]) -> None:
        transcurrido = 0.0
        while transcurrido < segundos:
            tramo = min(INTERVALO_DE_REVISION_S, segundos - transcurrido)
            esperar(tramo)
            transcurrido += tramo
            revisar()

    return _dictar(
        grabadora=grabadora,
        motor=motor,
        mientras_graba=esperar_el_tiempo,
        dispositivo=dispositivo,
        idioma=idioma,
        pista=pista,
        opciones=opciones,
        al_empezar=al_empezar,
    )


def dictar_hasta(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    seguir: Callable[[], bool],
    esperar: Callable[[float], None] = time.sleep,
    dispositivo: str | int | None = None,
    idioma: str | None = None,
    pista: str | None = None,
    opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO,
    al_empezar: Callable[[], None] | None = None,
) -> ResultadoDictado:
    """Como ``dictar_una_vez``, pero graba mientras ``seguir()`` sea verdadero."""

    def esperar_el_evento(revisar: Callable[[], None]) -> None:
        while seguir():
            esperar(INTERVALO_DE_REVISION_S)
            revisar()

    return _dictar(
        grabadora=grabadora,
        motor=motor,
        mientras_graba=esperar_el_evento,
        dispositivo=dispositivo,
        idioma=idioma,
        pista=pista,
        opciones=opciones,
        al_empezar=al_empezar,
    )


ARRANQUE_MAXIMO_MS = 150
"""Si empezar a grabar tarda más, la primera palabra se puede perder: habría que pre-grabar."""
_ESPERA_DE_LA_VENTANA_S = 0.1
_ESPERA_AL_DETENER_S = 15.0

_EVENTOS = {
    (AccionDeAtajo.MANTENER, FaseDeAtajo.PULSADO): Evento.PULSAR,
    (AccionDeAtajo.MANTENER, FaseDeAtajo.SOLTADO): Evento.SOLTAR,
    (AccionDeAtajo.TRADUCIR, FaseDeAtajo.PULSADO): Evento.PULSAR,
    (AccionDeAtajo.TRADUCIR, FaseDeAtajo.SOLTADO): Evento.SOLTAR,
    (AccionDeAtajo.ALTERNAR, FaseDeAtajo.PULSADO): Evento.ALTERNAR,
}


class Reescritura(Protocol):
    """Reescribe con un modelo de lenguaje si corresponde; ``ReescrituraDeBase`` la cumple."""

    def intentar(
        self, texto: str, modo: Modo, traducir_a: str | None = None
    ) -> ResultadoReescritura: ...


class RegistroDeDictados(Protocol):
    """Donde queda el historial; ``HistorialRepo`` lo cumple. Con el historial apagado no guarda."""

    def guardar(
        self,
        *,
        texto_crudo: str,
        texto_final: str,
        duracion_audio_ms: int,
        duracion_proceso_ms: int,
        estado: EstadoDelHistorial,
        idioma: str = "",
        aplicacion: str = "",
        modo_id: int | None = None,
        reescrito: bool = False,
        proveedor: str = "",
    ) -> object: ...


class Aplicacion:
    """Del atajo al texto insertado. Cada dictado corre en su propio hilo; los atajos llegan desde
    el hilo de la escucha y solo cambian el estado, sin bloquearse.

    Privacidad: ni el texto dictado ni el título de la ventana se registran jamás.
    """

    def __init__(
        self,
        *,
        escucha: EscuchaDeAtajos,
        grabadora: Grabadora,
        motor: MotorDeTranscripcion,
        ventana: VentanaActiva,
        insertor: Insertor,
        atajos: Mapping[AccionDeAtajo, str],
        idioma: str | None = None,
        dispositivo: str | int | None = None,
        configuracion: FuenteDeConfiguracion | None = None,
        historial: RegistroDeDictados | None = None,
        reescritura: Reescritura | None = None,
        al_cambiar_estado: Callable[[EstadoDelDictado], None] | None = None,
        al_aviso: Callable[[str], None] | None = None,
        al_texto_sin_insertar: Callable[[str], None] | None = None,
    ) -> None:
        self._escucha = escucha
        self._grabadora = grabadora
        self._motor = motor
        self._ventana = ventana
        self._insertor = insertor
        self._atajos = dict(atajos)
        self._configuracion = configuracion or ConfiguracionEstatica()
        self._historial = historial
        self._reescritura = reescritura
        self._idioma = idioma
        self._dispositivo = dispositivo
        self._soltado_s = 0.0
        self._guardado = False
        self._al_cambiar_estado = al_cambiar_estado
        self._al_aviso = al_aviso
        self._al_texto_sin_insertar = al_texto_sin_insertar
        self._candado = threading.RLock()
        self._dictado = EstadoDictado(al_cambiar=self._publicar)
        self._fin_de_grabacion = threading.Event()
        self._hilo: threading.Thread | None = None
        self._accion_inicial: AccionDeAtajo | None = None
        self._cancelado = False
        self.pausada = False
        self.idioma_en_curso: str | None = None
        """El idioma de destino mientras dura un dictado hecho con la tecla de traducir."""
        self._inicio_s = 0.0
        self._ventana_consultada: Future[InfoVentana | None] | None = None
        self.texto_sin_insertar: str | None = None
        self.ultimo_arranque_ms: int | None = None

    @property
    def estado(self) -> EstadoDelDictado:
        return self._dictado.estado

    # ---- ciclo de vida -----------------------------------------------------------------------

    def iniciar(self) -> None:
        """Carga el modelo (una sola vez) y empieza a escuchar los atajos."""
        self._motor.cargar()
        self._cancelado = False
        self._escucha.iniciar(self._atajos, self._al_atajo)

    def pausar(self, pausado: bool) -> None:
        """En pausa los atajos no empiezan dictados nuevos; soltar y terminar siguen andando."""
        self.pausada = pausado

    def reconfigurar_atajos(self, atajos: Mapping[AccionDeAtajo, str]) -> None:
        """Cambia las teclas en vivo, sin reiniciar. Si las nuevas no sirven, quedan las de antes.

        Lanza ``AtajoOcupado`` (u otro error de la escucha) con las nuevas y ``RuntimeError`` si
        hay un dictado en curso.
        """
        with self._candado:
            if self._dictado.estado not in (EstadoDelDictado.INACTIVO, EstadoDelDictado.ERROR):
                raise RuntimeError(
                    "Esperá a que termine el dictado en curso para cambiar las teclas"
                )
            anteriores = self._atajos
            self._escucha.detener()
            try:
                self._escucha.iniciar(dict(atajos), self._al_atajo)
            except Exception:
                self._escucha.iniciar(anteriores, self._al_atajo)  # vuelve a como estaba
                raise
            self._atajos = dict(atajos)

    def detener(self) -> None:
        self._escucha.detener()
        with self._candado:
            self._cancelado = True
            if self._dictado.estado is EstadoDelDictado.ESCUCHANDO:
                self._dictado.manejar(Evento.ALTERNAR)
            self._fin_de_grabacion.set()
            hilo = self._hilo
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(timeout=_ESPERA_AL_DETENER_S)
        self._motor.descargar()

    # ---- atajos ------------------------------------------------------------------------------

    def _al_atajo(self, evento: EventoDeAtajo) -> None:
        traducido = _EVENTOS.get((evento.accion, evento.fase))
        if traducido is None:
            return
        with self._candado:
            if self._cancelado:
                return
            escuchando = self._dictado.estado is EstadoDelDictado.ESCUCHANDO
            if self.pausada and not escuchando and traducido is not Evento.SOLTAR:
                return  # en pausa no se empiezan dictados nuevos
            if traducido is Evento.SOLTAR and escuchando and evento.accion != self._accion_inicial:
                return  # solo la tecla que empezó puede terminar (soltar otra no corta nada)
            anterior = self.idioma_en_curso
            if not escuchando and traducido is not Evento.SOLTAR:
                # Antes de cambiar el estado: quien lo escucha ya tiene que ver el idioma.
                self.idioma_en_curso = self._idioma_si_traduce(evento.accion)
            if not self._dictado.manejar(traducido):
                self.idioma_en_curso = anterior
                return
            if self._dictado.estado is EstadoDelDictado.ESCUCHANDO:
                self._empezar(evento.accion)
            elif escuchando:
                self._soltado_s = time.perf_counter()
                self._fin_de_grabacion.set()

    def _idioma_si_traduce(self, accion: AccionDeAtajo) -> str | None:
        if accion is not AccionDeAtajo.TRADUCIR:
            return None
        try:
            return self._configuracion.idioma_de_traduccion()
        except Exception:
            _registro.exception("No se pudo leer el idioma de traducción")
            return None

    def _empezar(self, accion: AccionDeAtajo) -> None:
        self._accion_inicial = accion
        self._inicio_s = time.perf_counter()
        self._fin_de_grabacion.clear()
        self._ventana_consultada = self._consultar_ventana()
        self._hilo = threading.Thread(
            target=self._dictar,
            args=(accion is AccionDeAtajo.TRADUCIR,),
            name="vozflow-dictado",
            daemon=True,
        )
        self._hilo.start()

    def _consultar_ventana(self) -> Future[InfoVentana | None]:
        futuro: Future[InfoVentana | None] = Future()

        def tarea() -> None:
            try:
                futuro.set_result(self._ventana.consultar())
            except Exception:
                _registro.debug("No se pudo consultar la ventana activa")
                futuro.set_result(None)

        threading.Thread(target=tarea, name="vozflow-ventana", daemon=True).start()
        return futuro

    # ---- un dictado --------------------------------------------------------------------------

    def _dictar(self, traduciendo: bool) -> None:
        self._guardado = False
        resultado: ResultadoDictado | None = None
        try:
            resultado = dictar_hasta(
                grabadora=self._grabadora,
                motor=self._motor,
                seguir=lambda: not self._fin_de_grabacion.is_set(),
                pista=self._leer_pista(),
                idioma=self._idioma,
                dispositivo=self._dispositivo,
                esperar=self._esperar_el_fin,
                al_empezar=self._al_empezar,
            )
            self._insertar(resultado, traduciendo)
        except Exception as error:
            if resultado is not None and not self._guardado:
                # Hubo texto y algo falló después: queda en el historial para no perderlo.
                self._guardar(resultado, resultado.transcripcion.texto, "error", None, None)
            self._fallar(_mensaje_del_fallo(error))

    def _leer_pista(self) -> str | None:
        """El diccionario se lee en cada dictado, así una palabra nueva rige enseguida."""
        try:
            return self._configuracion.pista()
        except Exception:
            _registro.exception("No se pudo leer el diccionario")
            return None

    def _esperar_el_fin(self, segundos: float) -> None:
        self._fin_de_grabacion.wait(segundos)

    def _al_empezar(self) -> None:
        self.ultimo_arranque_ms = round((time.perf_counter() - self._inicio_s) * 1000)
        if self.ultimo_arranque_ms > ARRANQUE_MAXIMO_MS:
            _registro.warning(
                "Empezar a grabar tardó %d ms: la primera palabra podría perderse",
                self.ultimo_arranque_ms,
            )

    def _insertar(self, dictado: ResultadoDictado, traduciendo: bool) -> None:
        transcripcion = dictado.transcripcion
        ventana = self._ventana_activa()
        resolucion = self._configuracion.resolver(ventana.aplicacion if ventana else None)
        opciones = resolucion.opciones
        # Los atajos de texto se expanden al final, después de reescribir o traducir.
        limpio = procesar(
            transcripcion.texto, transcripcion.idioma or None, replace(opciones, atajos=())
        )
        if self._cancelado or limpio.descartar or not limpio.texto.strip():
            self._evento(Evento.SIN_VOZ)
            return
        texto, proveedor = limpio.texto, ""
        if traduciendo or self._reescritura is not None:
            traducir_a = self._configuracion.idioma_de_traduccion() if traduciendo else None
            reescrito = self._reescribir(texto, resolucion.modo, traducir_a)
            if traduciendo and reescrito.fallo:
                self._no_se_pudo_traducir(dictado, limpio.texto, ventana, resolucion.modo.id)
                self._fallar(reescrito.aviso or "No se pudo traducir")
                return
            texto, proveedor = reescrito.texto, reescrito.proveedor
            if reescrito.aviso is not None:
                self._avisar(reescrito.aviso)
        texto = completar(texto, opciones)
        self._evento(Evento.TEXTO_LISTO)
        resultado = self._insertor.insertar(texto, resolucion.destino)
        estado: EstadoDelHistorial = "insertado" if resultado.insertado else "no_insertado"
        self._guardar(dictado, texto, estado, ventana, resolucion.modo.id, proveedor)
        if resultado.insertado:
            self._evento(Evento.INSERTADO)
            return
        self.texto_sin_insertar = texto
        if self._al_texto_sin_insertar is not None:
            self._al_texto_sin_insertar(texto)
        self._fallar(resultado.motivo or "No se pudo insertar el texto")

    def _reescribir(self, texto: str, modo: Modo, traducir_a: str | None) -> ResultadoReescritura:
        if self._reescritura is None:
            return ResultadoReescritura(
                texto,
                aviso="No se pudo traducir: la reescritura no está configurada. "
                "No se insertó nada; el texto quedó en el historial.",
                fallo=True,
            )
        return self._reescritura.intentar(texto, modo, traducir_a)

    def _no_se_pudo_traducir(
        self,
        dictado: ResultadoDictado,
        texto: str,
        ventana: InfoVentana | None,
        modo_id: int,
    ) -> None:
        """Nada en el idioma equivocado: el texto queda en el historial para recuperarlo."""
        self._guardar(dictado, texto, "no_insertado", ventana, modo_id)
        self.texto_sin_insertar = texto
        if self._al_texto_sin_insertar is not None:
            self._al_texto_sin_insertar(texto)

    def _guardar(
        self,
        dictado: ResultadoDictado,
        texto_final: str,
        estado: EstadoDelHistorial,
        ventana: InfoVentana | None,
        modo_id: int | None,
        proveedor: str = "",
    ) -> None:
        """Un fallo del historial nunca debe impedir ni deshacer el dictado."""
        self._guardado = True
        if self._historial is None:
            return
        proceso_ms = round((time.perf_counter() - self._soltado_s) * 1000)
        try:
            self._historial.guardar(
                texto_crudo=dictado.transcripcion.texto,
                texto_final=texto_final,
                duracion_audio_ms=max(1, round(dictado.segundos_grabados * 1000)),
                duracion_proceso_ms=max(0, proceso_ms),
                estado=estado,
                idioma=dictado.transcripcion.idioma,
                aplicacion=ventana.aplicacion if ventana else "",
                modo_id=modo_id,
                reescrito=bool(proveedor),
                proveedor=proveedor,
            )
        except Exception:
            _registro.exception("No se pudo guardar el dictado en el historial")

    def _ventana_activa(self) -> InfoVentana | None:
        futuro = self._ventana_consultada
        if futuro is None:
            return None
        try:
            return futuro.result(timeout=_ESPERA_DE_LA_VENTANA_S)
        except EsperaAgotada:
            return None

    def _fallar(self, mensaje: str) -> None:
        self._evento(Evento.FALLO)
        self._avisar(mensaje)

    def _avisar(self, mensaje: str) -> None:
        if self._al_aviso is not None:
            self._al_aviso(mensaje)

    def _evento(self, evento: Evento) -> None:
        with self._candado:
            self._dictado.manejar(evento)

    def _publicar(self, anterior: EstadoDelDictado, nuevo: EstadoDelDictado) -> None:
        if nuevo in (EstadoDelDictado.INACTIVO, EstadoDelDictado.ERROR):
            self.idioma_en_curso = None
        if self._al_cambiar_estado is not None:
            self._al_cambiar_estado(nuevo)


def _mensaje_del_fallo(error: Exception) -> str:
    if isinstance(error, ErrorDeTranscripcion | ErrorDeAudio):
        return str(error)  # estos mensajes están pensados para mostrarse tal cual
    _registro.exception("Falló un dictado")
    return f"Falló el dictado ({type(error).__name__})"
