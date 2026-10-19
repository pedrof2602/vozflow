"""Lo que tiene en común cada paso del asistente de primer uso."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PasoDelAsistente(QWidget):
    """Un paso: un título, algo que mostrar y, si hace falta, una condición para avanzar."""

    TITULO = ""
    cambio = Signal()
    """El paso lo emite cuando cambió si se puede avanzar (p. ej. al detectar un micrófono)."""

    def puede_avanzar(self) -> bool:
        return True

    def al_entrar(self) -> None:
        """Se llama cada vez que el paso pasa a verse."""

    def al_salir(self) -> None:
        """Se llama cuando el paso deja de verse (para soltar el micrófono, por ejemplo)."""
