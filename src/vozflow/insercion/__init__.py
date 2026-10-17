"""Inserción de texto en la ventana activa."""

from vozflow.insercion.insertor import InsertorPorTeclas
from vozflow.insercion.portal_remoto import TecladorPortal
from vozflow.insercion.portapapeles import PortapapelesWayland
from vozflow.insercion.ydotool import TecladorYdotool


def crear_insertor() -> InsertorPorTeclas:
    """Copia y pega con Shift+Insert, la línea base observada funcionando en este equipo.

    ``ydotool`` va primero porque no abre una sesión ni muestra el indicador de GNOME; el portal
    ``RemoteDesktop`` queda de respaldo por si ``ydotoold`` no está disponible.
    """
    return InsertorPorTeclas(PortapapelesWayland(), [TecladorYdotool(), TecladorPortal()])
