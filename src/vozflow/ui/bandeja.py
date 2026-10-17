"""Ícono de la bandeja del sistema con su menú (RF-028).

GNOME no trae bandeja por defecto: hace falta la extensión AppIndicator. Si no está, no es un
error: el estado se sigue publicando por ``estado_cambiado`` para que la ventana principal lo
muestre.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from vozflow.dominio.dictado import EstadoDelDictado
from vozflow.ui.estado import VistaDeEstado, vista_de
from vozflow.ui.iconos import icono_de


class Bandeja(QObject):
    estado_cambiado = Signal(object)
    """Emite la ``VistaDeEstado`` cada vez que cambia el estado."""

    def __init__(
        self,
        *,
        al_abrir_ajustes: Callable[[], None],
        al_abrir_historial: Callable[[], None],
        al_pausar: Callable[[bool], None],
        al_salir: Callable[[], None],
        crear_icono: Callable[[], Any] = QSystemTrayIcon,
        disponible: Callable[[], bool] = QSystemTrayIcon.isSystemTrayAvailable,
    ) -> None:
        super().__init__()
        self._al_pausar = al_pausar
        self.pausada = False
        self.vista_actual: VistaDeEstado = vista_de(EstadoDelDictado.INACTIVO)
        self.disponible = disponible()
        self.menu = QMenu()
        self._accion_pausar = self._agregar("Pausar", self._alternar_pausa)
        self.menu.removeAction(self._accion_pausar)
        self._agregar("Abrir ajustes", al_abrir_ajustes)
        self._agregar("Historial", al_abrir_historial)
        self.menu.addAction(self._accion_pausar)
        self.menu.addSeparator()
        self._agregar("Salir", al_salir)
        self._icono: Any = crear_icono() if self.disponible else None
        if self._icono is not None:
            self._icono.setContextMenu(self.menu)
            self._icono.activated.connect(self._al_activar)
            self._refrescar()
            self._icono.show()

    def establecer_estado(self, estado: EstadoDelDictado) -> None:
        self.vista_actual = vista_de(estado)
        self._refrescar()
        self.estado_cambiado.emit(self.vista_actual)

    def notificar(self, texto: str) -> None:
        """Un aviso del escritorio; sin bandeja no hay dónde mostrarlo (queda en la ventana)."""
        mostrar = getattr(self._icono, "showMessage", None)
        if mostrar is not None:
            mostrar("vozflow", texto)

    def cerrar(self) -> None:
        if self._icono is not None:
            self._icono.hide()

    # ---- internos -----------------------------------------------------------------------

    def _agregar(self, texto: str, accion: Callable[[], None]) -> QAction:
        creada = self.menu.addAction(texto)
        creada.triggered.connect(lambda _=False: accion())
        return creada

    def _alternar_pausa(self) -> None:
        self.pausada = not self.pausada
        self._accion_pausar.setText("Reanudar" if self.pausada else "Pausar")
        self._al_pausar(self.pausada)
        self._refrescar()

    def _al_activar(self, motivo: QSystemTrayIcon.ActivationReason) -> None:
        if motivo == QSystemTrayIcon.ActivationReason.Trigger:
            self.menu.actions()[0].trigger()  # «Abrir ajustes»

    def _refrescar(self) -> None:
        if self._icono is None:
            return
        self._icono.setIcon(icono_de(self.vista_actual))
        texto = f"vozflow — {self.vista_actual.texto}"
        self._icono.setToolTip(f"{texto} (en pausa)" if self.pausada else texto)
