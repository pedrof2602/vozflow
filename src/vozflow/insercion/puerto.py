"""Interfaz del insertor de texto (RF-015 a RF-018)."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from vozflow.dominio.comandos_voz import SaltoDeLinea


class AtajoDePegado(Enum):
    """La combinación que pega. Shift+Insert funciona en terminales y en casi todo lo demás."""

    SHIFT_INSERT = "shift+insert"
    CTRL_V = "ctrl+v"
    CTRL_SHIFT_V = "ctrl+shift+v"


@dataclass(frozen=True)
class Destino:
    atajo: AtajoDePegado = AtajoDePegado.SHIFT_INSERT
    salto_de_linea: SaltoDeLinea = "conservar"


@dataclass(frozen=True)
class ResultadoInsercion:
    insertado: bool
    motivo: str | None = None
    codigo: str = ""
    """Código del catálogo de mensajes; el ``motivo`` es técnico, para el registro."""

    @classmethod
    def exito(cls) -> ResultadoInsercion:
        return cls(True)

    @classmethod
    def fallido(cls, motivo: str, codigo: str = "generico") -> ResultadoInsercion:
        return cls(False, motivo, codigo)


class Insertor(Protocol):
    def insertar(self, texto: str, destino: Destino) -> ResultadoInsercion:
        """Nunca emite Enter, restaura el portapapeles y no lanza por una ventana cerrada."""
        ...


class FalloDeTeclado(Exception):
    """Un teclador no pudo mandar las teclas; el mensaje se puede mostrar tal cual."""


class Teclador(Protocol):
    def pulsar_combinacion(self, teclas: Sequence[int]) -> None:
        """Pulsa las teclas (keysyms) en orden y las suelta al revés. Lanza ``FalloDeTeclado``."""
        ...
