"""Cliente común de los portales de escritorio (``org.freedesktop.portal.*``) por D-Bus.

Lo usan los atajos globales y la inserción de texto. Resuelve lo que tienen en común:

- Registrar la aplicación una sola vez (el portal la identifica por ``vozflow.desktop``).
- El patrón de *solicitud*: se llama a un método, y la respuesta real llega después como una
  señal ``Request.Response`` en una ruta que se calcula de antemano con un ``handle_token``. Hay
  que suscribirse **antes** de llamar, o la respuesta puede llegar sin que nadie la escuche.
- Escuchar señales (``Activated``, ``Deactivated``).

La conexión de ``jeepney`` en modo bloqueante no admite hilos: cada hilo usa su propio cliente.
"""

import logging
import secrets
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

from jeepney import DBusAddress, HeaderFields, MatchRule, MessageType, message_bus, new_method_call
from jeepney.wrappers import Properties

from vozflow.escritorio import ID_DE_APLICACION, asegurar_entrada_de_escritorio

PORTAL_DESTINO = "org.freedesktop.portal.Desktop"
PORTAL_RUTA = "/org/freedesktop/portal/desktop"
INTERFAZ_REQUEST = "org.freedesktop.portal.Request"
INTERFAZ_REGISTRO = "org.freedesktop.host.portal.Registry"

ESPERA_DE_RESPUESTA_S = 120.0
"""El usuario puede estar leyendo un diálogo de permisos."""
ESPERA_DE_LLAMADA_S = 5.0
_COLA_DE_SENALES = 256

_registro = logging.getLogger(__name__)


class ErrorDePortal(Exception):
    """El portal rechazó la llamada o no respondió; el mensaje se puede mostrar tal cual."""


class SolicitudDenegada(ErrorDePortal):
    """La respuesta del portal tuvo un código distinto de 0."""

    def __init__(self, codigo: int) -> None:
        self.codigo = codigo
        if codigo == 1:
            super().__init__("La solicitud fue cancelada (código 1)")
        else:
            super().__init__(f"La solicitud falló en el escritorio (código {codigo})")


class ConexionDBus(Protocol):
    """Lo que se usa de ``jeepney.io.blocking.DBusConnection``."""

    unique_name: str

    def send_and_get_reply(self, mensaje: Any, *, timeout: float | None = None) -> Any: ...

    def filter(self, rule: Any, *, queue: deque[Any] | None = None, bufsize: int = 1) -> Any: ...

    def recv_until_filtered(self, queue: deque[Any], *, timeout: float | None = None) -> Any: ...

    def close(self) -> None: ...


def nuevo_token() -> str:
    """Token único para un ``handle_token`` o un ``session_handle_token``."""
    return f"vozflow_{secrets.token_hex(6)}"


def ruta_de_solicitud(nombre_unico: str, token: str) -> str:
    """Ruta en la que el portal emitirá ``Response`` para la solicitud con ese token."""
    remitente = nombre_unico.lstrip(":").replace(".", "_")
    return f"{PORTAL_RUTA}/request/{remitente}/{token}"


def valor(resultados: dict[str, Any], clave: str, por_defecto: Any = None) -> Any:
    """Valor de una clave de un ``a{sv}``, sin la envoltura de la variante."""
    variante = resultados.get(clave)
    return por_defecto if variante is None else variante[1]


@dataclass(frozen=True)
class Respuesta:
    codigo: int
    resultados: dict[str, Any]


@dataclass(frozen=True)
class Senal:
    miembro: str
    cuerpo: tuple[Any, ...]


class Suscripcion:
    """Señales de una interfaz. Se usa con ``with`` para darse de baja al terminar."""

    def __init__(self, cliente: ClientePortal, reglas: Sequence[MatchRule]) -> None:
        self._cliente = cliente
        self._reglas = list(reglas)
        self._cola: deque[Any] = deque(maxlen=_COLA_DE_SENALES)
        self._manejadores = [cliente._conexion.filter(r, queue=self._cola) for r in self._reglas]
        for manejador in self._manejadores:
            manejador.__enter__()
        for regla in self._reglas:
            cliente._enviar(message_bus.AddMatch(regla))

    def recibir(self, timeout_s: float | None = None) -> Senal | None:
        """La próxima señal, o ``None`` si no llegó ninguna en ``timeout_s`` segundos."""
        try:
            mensaje = self._cliente._conexion.recv_until_filtered(self._cola, timeout=timeout_s)
        except TimeoutError:
            return None
        return Senal(str(mensaje.header.fields[HeaderFields.member]), tuple(mensaje.body))

    def cerrar(self) -> None:
        for manejador in self._manejadores:
            manejador.__exit__(None, None, None)
        self._manejadores = []
        for regla in self._reglas:
            try:
                self._cliente._enviar(message_bus.RemoveMatch(regla))
            except ErrorDePortal:
                _registro.debug("No se pudo quitar la suscripción", exc_info=True)

    def __enter__(self) -> Suscripcion:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        self.cerrar()


class ClientePortal:
    def __init__(
        self,
        conexion: ConexionDBus,
        app_id: str = ID_DE_APLICACION,
        asegurar_entrada: Callable[[], Any] = asegurar_entrada_de_escritorio,
    ) -> None:
        self._conexion = conexion
        self._app_id = app_id
        self._asegurar_entrada = asegurar_entrada
        self._registrada = False

    @classmethod
    def abrir(cls, app_id: str = ID_DE_APLICACION) -> ClientePortal:
        """Abre una conexión nueva al bus de sesión."""
        from jeepney.io.blocking import open_dbus_connection

        return cls(open_dbus_connection(bus="SESSION"), app_id=app_id)

    @property
    def nombre_unico(self) -> str:
        return self._conexion.unique_name

    def cerrar(self) -> None:
        self._conexion.close()

    # ---- registro y versión ---------------------------------------------------------------

    def registrar_aplicacion(self) -> None:
        """Identifica la aplicación ante el portal; una sola vez por conexión."""
        if self._registrada:
            return
        try:
            self._registrar()
        except ErrorDePortal as error:
            if "already associated" in str(error):
                self._registrada = True
                return
            if "App info not found" not in str(error):
                raise
            self._asegurar_entrada()
            try:
                self._registrar()
            except ErrorDePortal as segundo:
                if "already associated" not in str(segundo):
                    raise ErrorDePortal(
                        f"El portal no reconoce a la aplicación: falta {self._app_id}.desktop "
                        f"en ~/.local/share/applications ({segundo})"
                    ) from segundo
        self._registrada = True

    def _registrar(self) -> None:
        destino = self._direccion(INTERFAZ_REGISTRO)
        self._enviar(new_method_call(destino, "Register", "sa{sv}", (self._app_id, {})))

    def version_de(self, interfaz: str) -> int:
        """Versión de una interfaz del portal; 0 si el portal no la ofrece."""
        try:
            respuesta = self._enviar(Properties(self._direccion(interfaz)).get("version"))
        except ErrorDePortal:
            return 0
        return int(respuesta.body[0][1])

    # ---- llamadas ----------------------------------------------------------------------------

    def solicitar(
        self,
        interfaz: str,
        metodo: str,
        firma: str,
        construir_cuerpo: Callable[[str], tuple[Any, ...]],
        *,
        ruta: str = PORTAL_RUTA,
        timeout_s: float = ESPERA_DE_RESPUESTA_S,
    ) -> Respuesta:
        """Llama a un método que responde por ``Request.Response`` y espera esa respuesta.

        ``construir_cuerpo`` recibe el ``handle_token`` que debe ir en las opciones.
        """
        token = nuevo_token()
        regla = MatchRule(
            type="signal",
            interface=INTERFAZ_REQUEST,
            member="Response",
            path=ruta_de_solicitud(self.nombre_unico, token),
        )
        with self._conexion.filter(regla) as cola:
            self._enviar(message_bus.AddMatch(regla))  # primero suscribirse, después llamar
            try:
                mensaje = new_method_call(
                    self._direccion(interfaz, ruta), metodo, firma, construir_cuerpo(token)
                )
                self._enviar(mensaje)
                try:
                    respuesta = self._conexion.recv_until_filtered(cola, timeout=timeout_s)
                except TimeoutError as error:
                    raise ErrorDePortal(
                        f"Se agotó el tiempo de espera de la respuesta del portal a {metodo} "
                        f"({timeout_s:g} s). ¿Quedó un diálogo del escritorio sin responder?"
                    ) from error
            finally:
                self._quitar_suscripcion(regla)
        codigo, resultados = respuesta.body
        if codigo != 0:
            raise SolicitudDenegada(int(codigo))
        return Respuesta(int(codigo), dict(resultados))

    def llamar(
        self,
        interfaz: str,
        metodo: str,
        firma: str,
        cuerpo: tuple[Any, ...],
        *,
        ruta: str = PORTAL_RUTA,
        timeout_s: float = 3.0,
    ) -> tuple[Any, ...]:
        """Llamada simple, sin respuesta por señal (por ejemplo ``NotifyKeyboardKeysym``)."""
        respuesta = self._enviar(
            new_method_call(self._direccion(interfaz, ruta), metodo, firma, cuerpo), timeout_s
        )
        return tuple(respuesta.body)

    def escuchar(
        self, interfaz: str, miembros: Sequence[str], *, ruta: str | None = None
    ) -> Suscripcion:
        """Se suscribe a las señales ``miembros`` de ``interfaz``."""
        reglas = [
            MatchRule(type="signal", interface=interfaz, member=miembro, path=ruta)
            for miembro in miembros
        ]
        return Suscripcion(self, reglas)

    # ---- internos --------------------------------------------------------------------------------

    @staticmethod
    def _direccion(interfaz: str, ruta: str = PORTAL_RUTA) -> DBusAddress:
        return DBusAddress(ruta, bus_name=PORTAL_DESTINO, interface=interfaz)

    def _enviar(self, mensaje: Any, timeout_s: float = ESPERA_DE_LLAMADA_S) -> Any:
        respuesta = self._conexion.send_and_get_reply(mensaje, timeout=timeout_s)
        if respuesta.header.message_type is MessageType.error:
            texto = respuesta.body[0] if respuesta.body else "error sin descripción"
            raise ErrorDePortal(str(texto))
        return respuesta

    def _quitar_suscripcion(self, regla: MatchRule) -> None:
        try:
            self._enviar(message_bus.RemoveMatch(regla))
        except ErrorDePortal:
            _registro.debug("No se pudo quitar la suscripción", exc_info=True)
