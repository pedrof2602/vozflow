"""Interfaz del reescritor con modelo de lenguaje (RF-023 a RF-026)."""

from typing import Protocol


class ReescrituraFallida(Exception):
    """No se pudo reescribir (red, tiempo, respuesta vacía, clave rechazada).

    El mensaje se puede mostrar tal cual: nunca incluye la clave de acceso ni el texto.
    """


class Reescritor(Protocol):
    def reescribir(self, texto: str, instruccion: str, tiempo_maximo_s: int) -> str:
        """Devuelve ``texto`` reescrito según ``instruccion``. Lanza ``ReescrituraFallida``."""
        ...
