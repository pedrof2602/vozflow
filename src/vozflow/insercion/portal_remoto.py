"""Teclas por el portal ``RemoteDesktop`` (protocolo observado en research.md, secciones 10 y 11).

La sesión se abre para cada pegado y se cierra enseguida: mientras está abierta GNOME muestra un
indicador en la barra superior, y a 800 caracteres por segundo se ve una fracción de segundo. El
permiso se recuerda con un token de restauración, así que el diálogo sale solo la primera vez.
"""

import contextlib
import logging
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

from vozflow import rutas
from vozflow.dbus_portal import ClientePortal, ErrorDePortal, SolicitudDenegada, nuevo_token, valor
from vozflow.insercion.puerto import FalloDeTeclado

_REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"
_SESION = "org.freedesktop.portal.Session"
_TECLADO = 1
_PERSISTIR_HASTA_REVOCAR = 2
_ESPERA_AUTORIZACION_S = 10.0
_ESPERA_TECLA_S = 3.0
_PAUSA_ENTRE_PULSAR_Y_SOLTAR_S = 0.02

_registro = logging.getLogger(__name__)


class TecladorPortal:
    def __init__(
        self,
        abrir_cliente: Callable[[], ClientePortal] = ClientePortal.abrir,
        ruta_token: Path | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self._abrir_cliente = abrir_cliente
        self._ruta_token = ruta_token or rutas.ruta_token_portal()
        self._dormir = dormir

    def pulsar_combinacion(self, teclas: Sequence[int]) -> None:
        if not teclas:
            return
        try:
            with self._sesion() as (cliente, sesion):
                self._pulsar(cliente, sesion, teclas)
        except SolicitudDenegada as error:
            raise FalloDeTeclado(
                "El escritorio denegó o canceló el permiso para escribir (vozflow necesita "
                "que se lo des una vez)"
            ) from error
        except ErrorDePortal as error:
            raise FalloDeTeclado(f"El portal de escritorio falló: {error}") from error

    # ---- internos -------------------------------------------------------------------------------

    @contextlib.contextmanager
    def _sesion(self) -> Iterator[tuple[ClientePortal, str]]:
        cliente = self._abrir_cliente()
        sesion: str | None = None
        try:
            cliente.registrar_aplicacion()
            sesion = self._iniciar(cliente)
            yield cliente, sesion
        finally:
            if sesion is not None:
                with contextlib.suppress(ErrorDePortal):
                    cliente.llamar(_SESION, "Close", "", (), ruta=sesion)
            cliente.cerrar()

    def _iniciar(self, cliente: ClientePortal) -> str:
        creada = cliente.solicitar(
            _REMOTE_DESKTOP,
            "CreateSession",
            "a{sv}",
            lambda t: ({"handle_token": ("s", t), "session_handle_token": ("s", nuevo_token())},),
            timeout_s=_ESPERA_AUTORIZACION_S,
        )
        sesion = str(valor(creada.resultados, "session_handle"))
        try:
            guardado = self._leer_token()
            extra = {"restore_token": ("s", guardado)} if guardado else {}
            cliente.solicitar(
                _REMOTE_DESKTOP,
                "SelectDevices",
                "oa{sv}",
                lambda t: (
                    sesion,
                    {
                        "handle_token": ("s", t),
                        "types": ("u", _TECLADO),
                        "persist_mode": ("u", _PERSISTIR_HASTA_REVOCAR),
                        **extra,
                    },
                ),
                timeout_s=_ESPERA_AUTORIZACION_S,
            )
            iniciada = cliente.solicitar(
                _REMOTE_DESKTOP,
                "Start",
                "osa{sv}",
                lambda t: (sesion, "", {"handle_token": ("s", t)}),
                timeout_s=_ESPERA_AUTORIZACION_S,
            )
        except BaseException:
            with contextlib.suppress(ErrorDePortal):
                cliente.llamar(_SESION, "Close", "", (), ruta=sesion)
            raise
        nuevo = valor(iniciada.resultados, "restore_token")
        if nuevo:
            self._guardar_token(str(nuevo))
        return sesion

    def _pulsar(self, cliente: ClientePortal, sesion: str, teclas: Sequence[int]) -> None:
        pulsadas: list[int] = []
        try:
            for tecla in teclas:
                self._notificar(cliente, sesion, tecla, 1)
                pulsadas.append(tecla)
            self._dormir(_PAUSA_ENTRE_PULSAR_Y_SOLTAR_S)
        finally:
            # Siempre se sueltan las que quedaron pulsadas, aunque algo haya fallado: una
            # tecla modificadora trabada molestaría en todo el escritorio.
            for tecla in reversed(pulsadas):
                try:
                    self._notificar(cliente, sesion, tecla, 0)
                except ErrorDePortal:
                    _registro.warning("No se pudo soltar una tecla tras un fallo")

    @staticmethod
    def _notificar(cliente: ClientePortal, sesion: str, keysym: int, estado: int) -> None:
        cliente.llamar(
            _REMOTE_DESKTOP,
            "NotifyKeyboardKeysym",
            "oa{sv}iu",
            (sesion, {}, keysym, estado),
            timeout_s=_ESPERA_TECLA_S,
        )

    def _leer_token(self) -> str | None:
        try:
            return self._ruta_token.read_text().strip() or None
        except OSError:
            return None

    def _guardar_token(self, token: str) -> None:
        rutas.asegurar(self._ruta_token.parent)
        self._ruta_token.write_text(token)
        self._ruta_token.chmod(0o600)
