"""Doble de una conexión D-Bus que se comporta como el portal de escritorio.

Usa mensajes reales de ``jeepney``. Respeta una propiedad importante del bus real: una señal solo
llega a quien ya estaba suscrito cuando se emitió, así que suscribirse *después* de llamar al
método pierde la respuesta.
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from jeepney import (
    DBusAddress,
    HeaderFields,
    MatchRule,
    Message,
    MessageFlag,
    new_error,
    new_method_call,
    new_method_return,
    new_signal,
)


@dataclass
class Guion:
    """Cómo responde el portal a un método."""

    retorno: tuple[Any, ...] = ()
    firma: str = ""
    error: str | None = None
    nombre_error: str = "org.freedesktop.DBus.Error.Failed"
    respuesta: tuple[int, dict[str, Any]] | None = None
    """Si está, el método dispara la señal ``Request.Response`` con ``(código, resultados)``."""


class _Filtro:
    def __init__(self, conexion: ConexionPortalFalsa, regla: MatchRule, cola: deque[Message]):
        self._conexion = conexion
        self._par = (regla, cola)

    def __enter__(self) -> deque[Message]:
        return self._par[1]

    def __exit__(self, *_: object) -> None:
        self._conexion._filtros.remove(self._par)


class ConexionPortalFalsa:
    unique_name = ":1.42"

    def __init__(self, guion: dict[str, Guion | list[Guion]] | None = None) -> None:
        self._guion = guion or {}
        self.registro: list[str] = []
        self.llamadas: list[Message] = []
        self._filtros: list[tuple[MatchRule, deque[Message]]] = []
        self.cerrada = False

    # ---- lo que usa el cliente ------------------------------------------------------------

    def send_and_get_reply(self, mensaje: Message, *, timeout: float | None = None) -> Message:
        miembro = str(mensaje.header.fields[HeaderFields.member])
        if miembro in ("AddMatch", "RemoveMatch"):
            self.registro.append(miembro)
            return new_method_return(mensaje)
        self.registro.append(f"llamada:{miembro}")
        self.llamadas.append(mensaje)
        guion = self._siguiente_guion(miembro)
        if guion.error is not None:
            return new_error(mensaje, guion.nombre_error, "s", (guion.error,))
        if guion.respuesta is not None:
            self._emitir_response(mensaje, *guion.respuesta)
        return new_method_return(mensaje, guion.firma or None, guion.retorno)

    def filter(
        self, rule: MatchRule, *, queue: deque[Message] | None = None, bufsize: int = 1
    ) -> _Filtro:
        cola: deque[Message] = queue if queue is not None else deque(maxlen=bufsize)
        self._filtros.append((rule, cola))
        return _Filtro(self, rule, cola)

    def recv_until_filtered(
        self, queue: deque[Message], *, timeout: float | None = None
    ) -> Message:
        if queue:
            return queue.popleft()
        raise TimeoutError

    def close(self) -> None:
        self.cerrada = True

    # ---- lo que usan las pruebas ------------------------------------------------------------

    def emitir(
        self, ruta: str, interfaz: str, miembro: str, firma: str, cuerpo: tuple[Any, ...]
    ) -> None:
        """Emite una señal del portal (por ejemplo ``Activated``)."""
        senal = new_signal(DBusAddress(ruta, interface=interfaz), miembro, firma, cuerpo)
        for regla, cola in self._filtros:
            if regla.matches(senal):
                cola.append(senal)

    def token_de(self, metodo: str) -> str:
        """El ``handle_token`` con que el cliente llamó a ``metodo``."""
        for mensaje in self.llamadas:
            if mensaje.header.fields[HeaderFields.member] == metodo:
                return self._token(mensaje)
        raise AssertionError(f"No se llamó a {metodo}")

    def llamadas_a(self, metodo: str) -> list[Message]:
        return [m for m in self.llamadas if m.header.fields[HeaderFields.member] == metodo]

    # ---- internos --------------------------------------------------------------------------------

    def _siguiente_guion(self, miembro: str) -> Guion:
        guion = self._guion.get(miembro, Guion())
        if isinstance(guion, list):
            return guion.pop(0) if len(guion) > 1 else guion[0]
        return guion

    @staticmethod
    def _token(mensaje: Message) -> str:
        for elemento in mensaje.body:
            if isinstance(elemento, dict) and "handle_token" in elemento:
                return str(elemento["handle_token"][1])
        raise AssertionError("La llamada no trae handle_token")

    def _emitir_response(self, mensaje: Message, codigo: int, resultados: dict[str, Any]) -> None:
        remitente = self.unique_name[1:].replace(".", "_")
        ruta = f"/org/freedesktop/portal/desktop/request/{remitente}/{self._token(mensaje)}"
        self.emitir(
            ruta, "org.freedesktop.portal.Request", "Response", "ua{sv}", (codigo, resultados)
        )


class ConexionServidorFalsa:
    unique_name = ":1.99"

    def __init__(self, codigo_del_nombre: int = 1) -> None:
        self.codigo_del_nombre = codigo_del_nombre
        self.entrantes: deque[Message] = deque()
        self.enviados: list[Message] = []
        self.peticiones: list[Message] = []
        self.cerrada = False

    def send_and_get_reply(self, mensaje: Message, *, timeout: float | None = None) -> Message:
        self.peticiones.append(mensaje)
        return new_method_return(mensaje, "u", (self.codigo_del_nombre,))

    def receive(self, *, timeout: float | None = None) -> Message:
        if self.entrantes:
            return self.entrantes.popleft()
        time.sleep(0.01)
        raise TimeoutError

    def send(self, mensaje: Message, serial: int | None = None) -> None:
        self.enviados.append(mensaje)

    def close(self) -> None:
        self.cerrada = True


def llamada_toggle(sin_respuesta: bool = False) -> Message:
    """Lo que manda ``dbus-send`` cuando GNOME detecta el atajo."""
    from vozflow.servicio_dbus import INTERFAZ, NOMBRE_DEL_SERVICIO, RUTA

    mensaje = new_method_call(
        DBusAddress(RUTA, bus_name=NOMBRE_DEL_SERVICIO, interface=INTERFAZ), "Toggle"
    )
    if sin_respuesta:
        mensaje.header.flags = MessageFlag.no_reply_expected
    return mensaje
