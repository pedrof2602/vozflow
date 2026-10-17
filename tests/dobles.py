"""Dobles de prueba compartidos por varias baterías."""

import contextlib
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from evdev import InputEvent, ecodes

from vozflow.atajos.puerto import (
    AccionDeAtajo,
    AtajoOcupado,
    Despachador,
    EventoDeAtajo,
    FaseDeAtajo,
)
from vozflow.audio.senal import Audio
from vozflow.insercion.puerto import Destino, ResultadoInsercion
from vozflow.transcripcion.motor import ErrorDeTranscripcion, Transcripcion, validar_audio
from vozflow.ventana.puerto import InfoVentana

_MENSAJE_NO_CARGADO: Final = "El motor no está cargado"


@dataclass(frozen=True)
class LlamadaATranscribir:
    muestras: int
    pista: str | None
    idioma: str | None


class MotorFalso:
    """Motor de transcripción que devuelve un texto fijo; cumple el contrato de ``motor.py``."""

    def __init__(
        self,
        texto: str = "hola mundo",
        idioma: str = "es",
        probabilidad_idioma: float = 0.99,
    ) -> None:
        self.texto = texto
        self.idioma = idioma
        self.probabilidad_idioma = probabilidad_idioma
        self.llamadas: list[LlamadaATranscribir] = []
        self.veces_cargado = 0
        self.cargado = False

    def cargar(self) -> None:
        self.cargado = True
        self.veces_cargado += 1

    def transcribir(self, audio: Audio, pista: str | None, idioma: str | None) -> Transcripcion:
        if not self.cargado:
            raise ErrorDeTranscripcion(_MENSAJE_NO_CARGADO)
        validar_audio(audio)
        self.llamadas.append(LlamadaATranscribir(len(audio), pista, idioma))
        if len(audio) == 0:
            return Transcripcion(texto="", idioma="", probabilidad_idioma=0.0, duracion_ms=0)
        return Transcripcion(
            texto=self.texto,
            idioma=idioma or self.idioma,
            probabilidad_idioma=self.probabilidad_idioma,
            duracion_ms=1,
        )

    def descargar(self) -> None:
        self.cargado = False


class EscuchaFalsa:
    """``EscuchaDeAtajos`` que no toca el sistema: la persona se simula con ``pulsar``/``soltar``."""

    def __init__(self) -> None:
        self._despachador: Despachador | None = None
        self._ocupados: set[str] = set()
        self.atajos_actuales: dict[AccionDeAtajo, str] = {}

    def ocupar(self, atajo: str) -> None:
        """Hace que otra función del escritorio ya use esta combinación."""
        self._ocupados.add(atajo)

    def iniciar(
        self, atajos: Mapping[AccionDeAtajo, str], al_evento: Callable[[EventoDeAtajo], None]
    ) -> None:
        if self._despachador is not None and self._despachador.activo:
            raise RuntimeError("La escucha ya está iniciada")
        for atajo in atajos.values():
            if atajo in self._ocupados:
                raise AtajoOcupado(f"{atajo} ya lo usa otra función del escritorio")
        self._despachador = Despachador(al_evento)
        self.atajos_actuales = dict(atajos)

    def detener(self) -> None:
        if self._despachador is not None:
            self._despachador.detener()

    def pulsar(self, accion: AccionDeAtajo) -> None:
        if self._despachador is not None:
            self._despachador.emitir(accion, FaseDeAtajo.PULSADO)

    def soltar(self, accion: AccionDeAtajo) -> None:
        if self._despachador is not None:
            self._despachador.emitir(accion, FaseDeAtajo.SOLTADO)


class TecladoFalso:
    """Un teclado que se puede ``select``ar: cada ``enviar`` escribe un byte en una tubería."""

    def __init__(self, ruta: str, nombre: str) -> None:
        self.ruta = ruta
        self.nombre = nombre
        self._lectura, self._escritura = os.pipe()
        self.fd = self._lectura
        self.eventos: list[InputEvent] = []
        self.cerrado = False
        self.desconectado = False

    def teclas(self) -> set[int]:
        return {ecodes.KEY_A, ecodes.KEY_LEFTCTRL, ecodes.KEY_SPACE}

    def enviar(self, *teclas: tuple[int, int]) -> None:
        for codigo, valor in teclas:
            self.eventos.append(InputEvent(0, 0, ecodes.EV_KEY, codigo, valor))
        os.write(self._escritura, b"x")

    def leer(self) -> list[InputEvent]:
        if self.desconectado:
            raise OSError(19, "No such device")
        os.read(self._lectura, 4096)
        pendientes, self.eventos = self.eventos, []
        return pendientes

    def cerrar(self) -> None:
        self.cerrado = True

    def grab(self) -> None:  # nunca debe llamarse: no se toma el teclado en exclusivo
        raise AssertionError("No se debe tomar el teclado en exclusivo (EVIOCGRAB)")

    def destruir(self) -> None:
        for descriptor in (self._lectura, self._escritura):
            with contextlib.suppress(OSError):
                os.close(descriptor)


class Reloj:
    def __init__(self) -> None:
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora


class GSettingsFalso:
    """Imita el comando ``gsettings`` con estado: ``get``, ``set``, ``reset-recursively`` y
    ``list-recursively``. Los valores se guardan en el texto GVariant que imprime la herramienta."""

    def __init__(self) -> None:
        self.valores: dict[tuple[str, str], str] = {}
        self.llamadas: list[tuple[str, ...]] = []
        self.fallar_con: Exception | None = None

    def precargar(self, esquema: str, clave: str, valor: str) -> None:
        self.valores[(esquema, clave)] = valor

    def __call__(self, argumentos: Sequence[str]) -> str:
        self.llamadas.append(tuple(argumentos))
        if self.fallar_con is not None:
            raise self.fallar_con
        orden, *resto = argumentos
        if orden == "get":
            esquema, clave = resto
            return self.valores.get((esquema, clave), self._por_defecto(clave)) + "\n"
        if orden == "set":
            esquema, clave, valor = resto
            self.valores[(esquema, clave)] = valor if valor.startswith(("[", "@")) else repr(valor)
            return ""
        if orden == "reset-recursively":
            (esquema,) = resto
            for llave in [k for k in self.valores if k[0] == esquema]:
                del self.valores[llave]
            return ""
        if orden == "list-recursively":
            (esquema,) = resto
            return "".join(f"{e} {c} {v}\n" for (e, c), v in self.valores.items() if e == esquema)
        raise AssertionError(f"Orden de gsettings no prevista: {argumentos}")

    @staticmethod
    def _por_defecto(clave: str) -> str:
        return "@as []" if clave == "custom-keybindings" else "''"


class GrabadoraFalsa:
    """Captura que «graba» una senoide de la duración pedida; cumple ``Grabadora``."""

    def __init__(self, segundos: float = 1.5, amplitud: float = 0.3) -> None:
        self.segundos = segundos
        self.amplitud = amplitud
        self.iniciadas = 0
        self.detenidas = 0
        self.fallar_al_iniciar: Exception | None = None

    def _audio(self) -> npt.NDArray[np.int16]:
        t = np.arange(int(16000 * self.segundos)) / 16000
        return (np.sin(2 * np.pi * 440 * t) * self.amplitud * 32767).astype(np.int16)

    def iniciar(self, dispositivo: str | int | None = None) -> None:
        if self.fallar_al_iniciar is not None:
            raise self.fallar_al_iniciar
        self.iniciadas += 1

    def audio_acumulado(self) -> npt.NDArray[np.int16]:
        return self._audio()

    def detener_crudo(self) -> npt.NDArray[np.int16]:
        self.detenidas += 1
        return self._audio()


class InsertorFalso:
    def __init__(self, resultado: ResultadoInsercion | None = None) -> None:
        self.resultado = resultado or ResultadoInsercion.exito()
        self.insertados: list[tuple[str, Destino]] = []

    def insertar(self, texto: str, destino: Destino) -> ResultadoInsercion:
        self.insertados.append((texto, destino))
        return self.resultado


class VentanaFalsa:
    def __init__(self, ventana: InfoVentana | None = None) -> None:
        self.ventana = ventana
        self.consultas = 0
        self.liberar = threading.Event()
        self.liberar.set()  # por defecto contesta al instante
        self.error: Exception | None = None

    def consultar(self) -> InfoVentana | None:
        self.consultas += 1
        self.liberar.wait(5)
        if self.error is not None:
            raise self.error
        return self.ventana


class ReescritorFalso:
    """``Reescritor`` que no toca la red: devuelve un texto fijo o falla de la forma pedida."""

    def __init__(self, resultado: str = "Texto reescrito.", fallo: str | None = None) -> None:
        from vozflow.llm.puerto import ReescrituraFallida  # evita un ciclo al importar

        self.resultado = resultado
        self.fallo = fallo
        self.llamadas: list[tuple[str, str, int]] = []
        self._error = ReescrituraFallida

    def reescribir(self, texto: str, instruccion: str, tiempo_maximo_s: int) -> str:
        self.llamadas.append((texto, instruccion, tiempo_maximo_s))
        if self.fallo is not None:
            raise self._error(self.fallo)
        return self.resultado
