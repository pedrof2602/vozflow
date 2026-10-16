"""Escucha de teclas leyendo ``/dev/input`` con evdev: el modo «mantener para hablar».

Un atajo de GNOME avisa al pulsar pero no al soltar; para saber cuándo soltaste hay que leer el
teclado. Por eso este módulo mira todas las teclas del sistema.

PRIVACIDAD: ve todo lo que se teclea. Solo compara cada tecla con la combinación configurada y
la descarta; **no registra ni guarda ninguna pulsación**, ni siquiera en los logs de depuración.
Tampoco toma el teclado en exclusivo (no usa ``EVIOCGRAB``): las teclas siguen llegando a las
demás aplicaciones.
"""

import contextlib
import logging
import os
import re
import selectors
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol

import evdev
from evdev import ecodes

from vozflow.atajos.puerto import (
    AccionDeAtajo,
    AlEvento,
    Despachador,
    EventoDeAtajo,
    FaseDeAtajo,
)

_registro = logging.getLogger(__name__)

ABAJO, ARRIBA, REPITE = 1, 0, 2
ESPERA_DEL_MODIFICADOR_SOLO_S = 0.25
"""Una tecla modificadora sola (Ctrl derecho) cuenta solo si se sostiene este tiempo sin tocar
otra tecla; así no se dispara cada vez que se usa en otro atajo (Ctrl derecho + C)."""
_BUSQUEDA_S = 2.0
_ESPERA_MAXIMA_S = 1.0


class SinPermisoDeTeclado(Exception):
    """No se puede leer ``/dev/input``; el mensaje explica cómo arreglarlo."""


class SinTeclados(Exception):
    """No hay ningún teclado que escuchar."""


# ---- nombres de tecla ----------------------

_GRUPOS: dict[str, tuple[int, int]] = {
    "ctrl": (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL),
    "alt": (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT),
    "shift": (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT),
    "super": (ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA),
}
_GRUPO_DE_CODIGO = {codigo: grupo for grupo, codigos in _GRUPOS.items() for codigo in codigos}
_ALIAS_DE_GRUPO = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "meta": "super",
    "win": "super",
    "windows": "super",
    "cmd": "super",
}
_CON_LADO = {
    f"{lado}{alias}": _GRUPOS[grupo][0 if lado in ("left", "l") else 1]
    for lado in ("left", "right", "l", "r")
    for alias, grupo in _ALIAS_DE_GRUPO.items()
} | {"altgr": ecodes.KEY_RIGHTALT}
_NOMBRES_DE_TECLA = {
    "space": "SPACE",
    "espacio": "SPACE",
    "esc": "ESC",
    "escape": "ESC",
    "return": "ENTER",
    "enter": "ENTER",
    "grave": "GRAVE",
    "backtick": "GRAVE",
    "del": "DELETE",
    "ins": "INSERT",
}


@dataclass(frozen=True)
class Combinacion:
    tecla: int
    """Código evdev de la tecla principal (o del modificador, si va solo)."""
    modificadores: frozenset[str]
    """Grupos de modificadores que deben estar apretados, exactamente (``ctrl``, ``alt``…)."""
    solo_modificador: bool


def _codigo_de_tecla(nombre: str) -> int:
    clave = f"KEY_{_NOMBRES_DE_TECLA.get(nombre, nombre.upper())}"
    codigo = ecodes.ecodes.get(clave)
    if not isinstance(codigo, int):
        raise ValueError(f"No existe la tecla {nombre!r}")
    return codigo


def parsear_atajo(texto: str) -> Combinacion:
    """Entiende ``RightCtrl``, ``Ctrl+Alt+Space``, ``<Control><Alt>space`` y ``CTRL+ALT+d``."""
    nombres = [t.lower() for t in re.split(r"[+<>\s]+", texto.strip()) if t]
    if not nombres:
        raise ValueError("El atajo no tiene ninguna tecla")
    if len(nombres) == 1 and nombres[0] in _CON_LADO:
        return Combinacion(_CON_LADO[nombres[0]], frozenset(), solo_modificador=True)
    *modificadores, principal = nombres
    grupos: set[str] = set()
    for nombre in modificadores:
        if nombre not in _ALIAS_DE_GRUPO:
            raise ValueError(f"No existe el modificador {nombre!r} en el atajo {texto!r}")
        grupos.add(_ALIAS_DE_GRUPO[nombre])
    if principal in _ALIAS_DE_GRUPO or principal in _CON_LADO:
        raise ValueError(
            f"Al atajo {texto!r} le falta la tecla principal (solo tiene modificadores; "
            "un modificador solo debe indicar el lado, por ejemplo RightCtrl)"
        )
    return Combinacion(_codigo_de_tecla(principal), frozenset(grupos), solo_modificador=False)


# ---- máquina de estados ----------------------


class _Estado(Enum):
    INACTIVA = auto()
    PENDIENTE = auto()  # un modificador solo esperando los 250 ms
    ACTIVA = auto()


class MaquinaDeTeclas:
    """Decide cuándo una combinación está apretada. No lee nada ni usa hilos: es lógica pura."""

    def __init__(self, acciones: Mapping[AccionDeAtajo, Combinacion]) -> None:
        self._acciones = dict(acciones)
        self._apretadas: dict[str, set[int]] = {}
        self._estado = {accion: _Estado.INACTIVA for accion in self._acciones}
        self._vence: dict[AccionDeAtajo, float] = {}

    # ---- entrada ----------------------

    def tecla(self, dispositivo: str, codigo: int, valor: int, ahora: float) -> list[EventoDeAtajo]:
        if valor == ABAJO:
            antes = self._todas()
            self._apretadas.setdefault(dispositivo, set()).add(codigo)
            return self._al_apretar(codigo, antes, ahora)
        if valor == ARRIBA:
            self._apretadas.get(dispositivo, set()).discard(codigo)
            return self._al_soltar(codigo)
        return []  # REPITE u otro valor: una tecla mantenida no es una pulsación nueva

    def tick(self, ahora: float) -> list[EventoDeAtajo]:
        eventos: list[EventoDeAtajo] = []
        for accion in [a for a, vence in self._vence.items() if ahora >= vence]:
            del self._vence[accion]
            combinacion = self._acciones[accion]
            if self._estado[accion] is _Estado.PENDIENTE and self._todas() == {combinacion.tecla}:
                self._estado[accion] = _Estado.ACTIVA
                eventos.append(EventoDeAtajo(accion, FaseDeAtajo.PULSADO))
            else:
                self._estado[accion] = _Estado.INACTIVA
        return eventos

    def vencimiento(self) -> float | None:
        """Cuándo hay que volver a llamar a ``tick``; ``None`` si no hay nada pendiente."""
        return min(self._vence.values(), default=None)

    def dispositivo_perdido(self, dispositivo: str, ahora: float) -> list[EventoDeAtajo]:
        """Un teclado se desconectó: se sueltan sus teclas para no dejar ninguna «pegada»."""
        eventos: list[EventoDeAtajo] = []
        for codigo in sorted(self._apretadas.pop(dispositivo, set())):
            eventos += self._al_soltar(codigo)
        return eventos

    # ---- internos ----------------------

    def _todas(self) -> set[int]:
        return set().union(*self._apretadas.values()) if self._apretadas else set()

    def _grupos_apretados(self) -> set[str]:
        return {g for c in self._todas() if (g := _GRUPO_DE_CODIGO.get(c)) is not None}

    def _al_apretar(self, codigo: int, antes: set[int], ahora: float) -> list[EventoDeAtajo]:
        eventos: list[EventoDeAtajo] = []
        for accion, combinacion in self._acciones.items():
            estado = self._estado[accion]
            if combinacion.solo_modificador:
                if estado is _Estado.INACTIVA and codigo == combinacion.tecla and not antes:
                    self._estado[accion] = _Estado.PENDIENTE
                    self._vence[accion] = ahora + ESPERA_DEL_MODIFICADOR_SOLO_S
                elif estado is _Estado.PENDIENTE and codigo != combinacion.tecla:
                    self._cancelar(accion)  # era parte de otro atajo, como Ctrl derecho + C
            elif (
                estado is _Estado.INACTIVA
                and codigo == combinacion.tecla
                and self._grupos_apretados() == combinacion.modificadores
            ):
                self._estado[accion] = _Estado.ACTIVA
                eventos.append(EventoDeAtajo(accion, FaseDeAtajo.PULSADO))
        return eventos

    def _al_soltar(self, codigo: int) -> list[EventoDeAtajo]:
        if codigo in self._todas():  # otro teclado la sigue apretando
            return []
        eventos: list[EventoDeAtajo] = []
        for accion, combinacion in self._acciones.items():
            estado = self._estado[accion]
            if estado is _Estado.PENDIENTE and codigo == combinacion.tecla:
                self._cancelar(accion)
            elif estado is _Estado.ACTIVA and self._suelta(combinacion, codigo):
                self._estado[accion] = _Estado.INACTIVA
                eventos.append(EventoDeAtajo(accion, FaseDeAtajo.SOLTADO))
        return eventos

    def _suelta(self, combinacion: Combinacion, codigo: int) -> bool:
        if codigo == combinacion.tecla:
            return True
        grupo = _GRUPO_DE_CODIGO.get(codigo)
        return grupo in combinacion.modificadores and grupo not in self._grupos_apretados()

    def _cancelar(self, accion: AccionDeAtajo) -> None:
        self._estado[accion] = _Estado.INACTIVA
        self._vence.pop(accion, None)


# ---- dispositivos ----------------------


def es_teclado_real(nombre: str, teclas: set[int]) -> bool:
    """Un teclado de verdad: no el virtual de ``ydotoold`` (se dispararía con lo que vozflow
    mismo escribe) ni los botones de encendido o de cámara."""
    minusculas = nombre.lower()
    if "ydotool" in minusculas or "virtual" in minusculas:
        return False
    return ecodes.KEY_A in teclas and ecodes.KEY_SPACE in teclas


class DispositivoDeEntrada(Protocol):
    ruta: str
    nombre: str
    fd: int

    def teclas(self) -> set[int]: ...

    def leer(self) -> Iterable[Any]: ...

    def cerrar(self) -> None: ...


class _DispositivoReal:
    def __init__(self, dispositivo: Any) -> None:
        self._dispositivo = dispositivo
        self.ruta: str = dispositivo.path
        self.nombre: str = dispositivo.name
        self.fd: int = dispositivo.fd

    def teclas(self) -> set[int]:
        return set(self._dispositivo.capabilities().get(ecodes.EV_KEY, []))

    def leer(self) -> list[Any]:
        try:
            return list(self._dispositivo.read())
        except BlockingIOError:
            return []

    def cerrar(self) -> None:
        self._dispositivo.close()


class ListadorDeTeclados:
    """Abre los dispositivos de ``/dev/input`` y recuerda los que ya abrió."""

    def __init__(
        self,
        listar_rutas: Callable[[], list[str]] = evdev.list_devices,
        abrir: Callable[[str], Any] = evdev.InputDevice,
    ) -> None:
        self._listar_rutas = listar_rutas
        self._abrir = abrir
        self._abiertos: dict[str, _DispositivoReal] = {}

    def __call__(self) -> list[DispositivoDeEntrada]:
        rutas = set(self._listar_rutas())
        for ruta in set(self._abiertos) - rutas:
            del self._abiertos[ruta]
        sin_permiso = 0
        for ruta in sorted(rutas - set(self._abiertos)):
            try:
                self._abiertos[ruta] = _DispositivoReal(self._abrir(ruta))
            except PermissionError:
                sin_permiso += 1
            except OSError:
                _registro.debug("No se pudo abrir un dispositivo de entrada", exc_info=True)
        if not self._abiertos and sin_permiso:
            raise SinPermisoDeTeclado(
                "No se puede leer el teclado (/dev/input). Agregá tu usuario al grupo 'input' "
                "con: sudo usermod -aG input $USER, y volvé a iniciar sesión."
            )
        return list(self._abiertos.values())


# ---- la escucha ----------------------


class EscuchaEvdev:
    def __init__(
        self,
        listar_dispositivos: Callable[[], list[DispositivoDeEntrada]] | None = None,
        reloj: Callable[[], float] = time.monotonic,
        intervalo_de_busqueda_s: float = _BUSQUEDA_S,
        con_hilo: bool = True,
    ) -> None:
        self._listar = listar_dispositivos or ListadorDeTeclados()
        self._reloj = reloj
        self._intervalo = intervalo_de_busqueda_s
        self._con_hilo = con_hilo
        self._iniciada = False
        self._maquina: MaquinaDeTeclas | None = None
        self._despachador: Despachador | None = None
        self._selector: selectors.BaseSelector | None = None
        self._conocidos: dict[str, DispositivoDeEntrada] = {}
        self._rechazados: set[str] = set()
        self._proxima_busqueda = 0.0
        self._hilo: threading.Thread | None = None
        self._despertar: tuple[int, int] | None = None
        self._parar = threading.Event()

    def iniciar(self, atajos: Mapping[AccionDeAtajo, str], al_evento: AlEvento) -> None:
        if self._iniciada:
            raise RuntimeError("La escucha ya está iniciada")
        combinaciones = {accion: parsear_atajo(texto) for accion, texto in atajos.items()}
        self._selector = selectors.DefaultSelector()
        try:
            self._buscar_dispositivos()
            if not self._conocidos:
                raise SinTeclados("No se encontró ningún teclado para escuchar")
        except BaseException:
            self._cerrar_todo()
            raise
        self._maquina = MaquinaDeTeclas(combinaciones)
        self._despachador = Despachador(al_evento)
        self._proxima_busqueda = self._reloj() + self._intervalo
        self._parar.clear()
        self._despertar = os.pipe()
        self._selector.register(self._despertar[0], selectors.EVENT_READ, None)
        self._iniciada = True
        if self._con_hilo:
            self._hilo = threading.Thread(target=self._bucle, name="vozflow-evdev", daemon=True)
            self._hilo.start()

    def detener(self) -> None:
        if not self._iniciada:
            return
        self._iniciada = False
        self._parar.set()
        if self._despertar is not None:
            os.write(self._despertar[1], b"x")
        if self._hilo is not None:
            self._hilo.join(timeout=3.0)
            self._hilo = None
        if self._despachador is not None:
            self._despachador.detener()
        self._cerrar_todo()

    def bombear(self, timeout: float = 0.0) -> None:
        """Un ciclo de lectura: busca dispositivos nuevos, lee lo pendiente y avanza el reloj."""
        if not self._iniciada or self._selector is None or self._maquina is None:
            return
        ahora = self._reloj()
        if ahora >= self._proxima_busqueda:
            self._proxima_busqueda = ahora + self._intervalo
            self._buscar_dispositivos()
        salida: list[EventoDeAtajo] = []
        for clave, _ in self._selector.select(timeout):
            if clave.data is None:
                if self._despertar is not None:
                    os.read(self._despertar[0], 4096)
                continue
            salida += self._leer(clave.data, ahora)
        salida += self._maquina.tick(ahora)
        if self._despachador is not None:
            for evento in salida:
                self._despachador.emitir(evento.accion, evento.fase)

    # ---- internos ----------------------

    def _bucle(self) -> None:
        while not self._parar.is_set():
            ahora = self._reloj()
            esperas = [self._proxima_busqueda - ahora, _ESPERA_MAXIMA_S]
            if self._maquina is not None and (vence := self._maquina.vencimiento()) is not None:
                esperas.append(vence - ahora)
            try:
                self.bombear(timeout=max(0.0, min(esperas)))
            except Exception:
                _registro.exception("Falló un ciclo de la escucha de teclas")
                self._parar.wait(0.5)

    def _buscar_dispositivos(self) -> None:
        try:
            actuales = self._listar()
        except SinPermisoDeTeclado:
            if self._iniciada:
                _registro.warning("Se perdió el permiso para leer el teclado")
                return
            raise
        rutas = {d.ruta for d in actuales}
        for ruta in set(self._conocidos) - rutas:
            self._olvidar(ruta)
        for dispositivo in actuales:
            if dispositivo.ruta in self._conocidos or dispositivo.ruta in self._rechazados:
                continue
            if not es_teclado_real(dispositivo.nombre, dispositivo.teclas()):
                self._rechazados.add(dispositivo.ruta)
                dispositivo.cerrar()
                continue
            self._conocidos[dispositivo.ruta] = dispositivo
            if self._selector is not None:
                self._selector.register(dispositivo.fd, selectors.EVENT_READ, dispositivo)
            _registro.info("Escuchando el teclado %s", dispositivo.nombre)
        self._rechazados &= rutas

    def _leer(self, dispositivo: DispositivoDeEntrada, ahora: float) -> list[EventoDeAtajo]:
        if self._maquina is None:
            return []
        try:
            lectura = list(dispositivo.leer())
        except OSError:
            return self._olvidar(dispositivo.ruta, ahora)
        eventos: list[EventoDeAtajo] = []
        for evento in lectura:
            if evento.type == ecodes.EV_KEY:
                eventos += self._maquina.tecla(dispositivo.ruta, evento.code, evento.value, ahora)
        return eventos

    def _olvidar(self, ruta: str, ahora: float | None = None) -> list[EventoDeAtajo]:
        dispositivo = self._conocidos.pop(ruta, None)
        if dispositivo is None:
            return []
        if self._selector is not None:
            with contextlib.suppress(KeyError, ValueError, OSError):
                self._selector.unregister(dispositivo.fd)
        with contextlib.suppress(OSError):
            dispositivo.cerrar()
        _registro.info("Se desconectó el teclado %s", dispositivo.nombre)
        if self._maquina is None:
            return []
        eventos = self._maquina.dispositivo_perdido(ruta, self._reloj() if ahora is None else ahora)
        if self._despachador is not None and ahora is None:
            for evento in eventos:
                self._despachador.emitir(evento.accion, evento.fase)
            return []
        return eventos

    def _cerrar_todo(self) -> None:
        for ruta in list(self._conocidos):
            dispositivo = self._conocidos.pop(ruta)
            with contextlib.suppress(OSError):
                dispositivo.cerrar()
        if self._despertar is not None:
            for descriptor in self._despertar:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            self._despertar = None
        if self._selector is not None:
            self._selector.close()
            self._selector = None
        self._rechazados.clear()
