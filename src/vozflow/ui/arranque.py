"""Lo que hace falta antes de abrir la interfaz: una sola instancia (más lo de ``autoinicio``)."""

from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from vozflow.autoinicio import (
    activar_autoinicio,
    autoinicio_activo,
    desactivar_autoinicio,
    elegir_plataforma,
    fijar_plataforma,
)

__all__ = [
    "InstanciaUnica",
    "activar_autoinicio",
    "autoinicio_activo",
    "desactivar_autoinicio",
    "elegir_plataforma",
    "fijar_plataforma",
]

_ESPERA_AL_AVISAR_MS = 1000


class InstanciaUnica(QObject):
    """Un candado de archivo más un socket local: la segunda instancia le pide a la primera que
    muestre su ventana en lugar de arrancar otra."""

    pedido_de_mostrar = Signal()

    def __init__(self, nombre: str, directorio: Path) -> None:
        super().__init__()
        self._nombre = nombre
        self._candado = QLockFile(str(directorio / f"{nombre}.lock"))
        self._candado.setStaleLockTime(0)  # un candado de un proceso muerto no cuenta
        self._servidor: QLocalServer | None = None

    def obtener(self) -> bool:
        if not self._candado.tryLock(0):
            return False
        QLocalServer.removeServer(self._nombre)
        servidor = QLocalServer(self)
        servidor.newConnection.connect(self._al_conectar)
        servidor.listen(self._nombre)
        self._servidor = servidor
        return True

    def avisar_a_la_primera(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._nombre)
        if not socket.waitForConnected(_ESPERA_AL_AVISAR_MS):
            return False
        socket.write(b"mostrar")
        socket.flush()
        socket.waitForBytesWritten(_ESPERA_AL_AVISAR_MS)
        socket.disconnectFromServer()
        return True

    def liberar(self) -> None:
        if self._servidor is not None:
            self._servidor.close()
            self._servidor = None
        self._candado.unlock()

    def _al_conectar(self) -> None:
        if self._servidor is None:
            return
        while (conexion := self._servidor.nextPendingConnection()) is not None:
            conexion.close()
            self.pedido_de_mostrar.emit()
