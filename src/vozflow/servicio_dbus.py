"""Servicio D-Bus de vozflow: lo que llama el atajo de GNOME para alternar el dictado.

El atajo ejecuta ``dbus-send ... com.vozflow.App.Toggle``; este servicio lo recibe y avisa. El
nombre ``com.vozflow.App`` también garantiza que haya **una sola instancia**: si ya está tomado,
otra vozflow está corriendo.
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

from jeepney import (
    HeaderFields,
    MessageFlag,
    MessageType,
    message_bus,
    new_error,
    new_method_return,
)
from jeepney.io.blocking import open_dbus_connection

NOMBRE_DEL_SERVICIO = "com.vozflow.App"
RUTA = "/com/vozflow/App"
INTERFAZ = "com.vozflow.App"

_NO_PONERSE_EN_COLA = 4
_DUENO_PRINCIPAL, _YA_ERA_DUENO = 1, 4
_ESPERA_S = 0.2
_INTROSPECCION = f"""<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="{INTERFAZ}">
    <method name="Toggle"/>
  </interface>
</node>"""

_registro = logging.getLogger(__name__)


class InstanciaYaEnEjecucion(Exception):
    """Otra vozflow ya tiene el nombre del servicio en el bus."""


class ServicioDBus:
    def __init__(
        self,
        al_alternar: Callable[[], None],
        nombre: str = NOMBRE_DEL_SERVICIO,
        abrir_conexion: Callable[[], Any] | None = None,
    ) -> None:
        self._al_alternar = al_alternar
        self._nombre = nombre
        self._abrir = abrir_conexion or (lambda: open_dbus_connection(bus="SESSION"))
        self._conexion: Any = None
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()

    def iniciar(self) -> None:
        if self._hilo is not None:
            raise RuntimeError("El servicio ya está iniciado")
        conexion = self._abrir()
        try:
            respuesta = conexion.send_and_get_reply(
                message_bus.RequestName(self._nombre, _NO_PONERSE_EN_COLA), timeout=5.0
            )
            codigo = respuesta.body[0] if respuesta.body else 0
            if codigo not in (_DUENO_PRINCIPAL, _YA_ERA_DUENO):
                raise InstanciaYaEnEjecucion(
                    f"vozflow ya está corriendo (otro proceso tiene el nombre {self._nombre})"
                )
        except BaseException:
            conexion.close()
            raise
        self._conexion = conexion
        self._parar.clear()
        self._hilo = threading.Thread(target=self._servir, name="vozflow-dbus", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        if self._hilo is None:
            return
        self._parar.set()
        self._hilo.join(timeout=3.0)
        self._hilo = None
        self._conexion.close()
        self._conexion = None

    # ---- internos ------------------------------------------------------------------------------

    def _servir(self) -> None:
        while not self._parar.is_set():
            try:
                mensaje = self._conexion.receive(timeout=_ESPERA_S)
            except TimeoutError:
                continue
            except Exception:
                _registro.exception("Se perdió la conexión del servicio D-Bus")
                return
            try:
                self._atender(mensaje)
            except Exception:
                _registro.exception("Falló al atender una llamada D-Bus")

    def _atender(self, mensaje: Any) -> None:
        if mensaje.header.message_type is not MessageType.method_call:
            return
        campos = mensaje.header.fields
        ruta = campos.get(HeaderFields.path)
        interfaz = campos.get(HeaderFields.interface)
        miembro = campos.get(HeaderFields.member)
        if interfaz == "org.freedesktop.DBus.Peer" and miembro == "Ping":
            self._responder(mensaje, new_method_return(mensaje))
        elif interfaz == "org.freedesktop.DBus.Introspectable" and miembro == "Introspect":
            self._responder(mensaje, new_method_return(mensaje, "s", (_INTROSPECCION,)))
        elif ruta != RUTA:
            self._error(mensaje, "UnknownObject", f"No hay ningún objeto en {ruta}")
        elif interfaz == INTERFAZ and miembro == "Toggle":
            try:
                self._al_alternar()
            except Exception:
                _registro.exception("Falló quien recibe el aviso de alternar")
                self._error(mensaje, "Failed", "No se pudo alternar el dictado")
            else:
                self._responder(mensaje, new_method_return(mensaje))
        else:
            self._error(mensaje, "UnknownMethod", f"No existe el método {interfaz}.{miembro}")

    def _error(self, mensaje: Any, nombre: str, texto: str) -> None:
        self._responder(
            mensaje, new_error(mensaje, f"org.freedesktop.DBus.Error.{nombre}", "s", (texto,))
        )

    def _responder(self, mensaje: Any, respuesta: Any) -> None:
        # `dbus-send` sin --print-reply avisa que no espera respuesta: no se le manda.
        if mensaje.header.flags & MessageFlag.no_reply_expected:
            return
        self._conexion.send(respuesta)
