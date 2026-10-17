"""Interfaz de la ventana activa (RF-017, RF-021)."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class InfoVentana:
    aplicacion: str
    # El título puede tener datos personales: no sale en repr ni en registros.
    titulo: str = field(repr=False)
    pid: int


class VentanaActiva(Protocol):
    def consultar(self) -> InfoVentana | None:
        """La ventana con el foco, o ``None`` si no se puede identificar a tiempo."""
        ...
