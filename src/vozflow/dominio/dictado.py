"""Máquina de estados de un dictado (data-model.md, «Estados de un dictado»).

Es lógica pura: no sabe de teclas, audio ni ventanas. Quien la usa traduce lo que
pasa en el sistema a ``Evento`` y reacciona a los cambios de estado.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto


class EstadoDelDictado(Enum):
    INACTIVO = auto()
    ESCUCHANDO = auto()
    TRANSCRIBIENDO = auto()
    INSERTANDO = auto()
    ERROR = auto()


class Evento(Enum):
    # Del usuario: pueden llegar en cualquier momento y se ignoran si no aplican.
    PULSAR = auto()
    SOLTAR = auto()
    ALTERNAR = auto()
    # Internos: solo llegan cuando corresponden; fuera de lugar son un error de programa.
    SIN_VOZ = auto()
    TEXTO_LISTO = auto()
    INSERTADO = auto()
    FALLO = auto()
    REINICIAR = auto()


class TransicionInvalida(Exception):
    """Un evento interno llegó en un estado en el que no puede ocurrir."""


_DEL_USUARIO = frozenset({Evento.PULSAR, Evento.SOLTAR, Evento.ALTERNAR})

E = EstadoDelDictado
_TRANSICIONES: dict[tuple[EstadoDelDictado, Evento], EstadoDelDictado] = {
    (E.INACTIVO, Evento.PULSAR): E.ESCUCHANDO,
    (E.INACTIVO, Evento.ALTERNAR): E.ESCUCHANDO,
    (E.ERROR, Evento.PULSAR): E.ESCUCHANDO,
    (E.ERROR, Evento.ALTERNAR): E.ESCUCHANDO,
    (E.ESCUCHANDO, Evento.SOLTAR): E.TRANSCRIBIENDO,
    (E.ESCUCHANDO, Evento.ALTERNAR): E.TRANSCRIBIENDO,
    (E.ESCUCHANDO, Evento.SIN_VOZ): E.INACTIVO,
    (E.TRANSCRIBIENDO, Evento.SIN_VOZ): E.INACTIVO,
    (E.TRANSCRIBIENDO, Evento.TEXTO_LISTO): E.INSERTANDO,
    (E.INSERTANDO, Evento.INSERTADO): E.INACTIVO,
    (E.ESCUCHANDO, Evento.FALLO): E.ERROR,
    (E.TRANSCRIBIENDO, Evento.FALLO): E.ERROR,
    (E.INSERTANDO, Evento.FALLO): E.ERROR,
    (E.ERROR, Evento.REINICIAR): E.INACTIVO,
}
del E


@dataclass
class EstadoDictado:
    """Estado actual de un dictado y sus transiciones permitidas."""

    al_cambiar: Callable[[EstadoDelDictado, EstadoDelDictado], None] | None = None
    estado: EstadoDelDictado = EstadoDelDictado.INACTIVO

    def manejar(self, evento: Evento) -> bool:
        """Aplica un evento. Devuelve ``True`` si cambió el estado.

        Un evento del usuario que no aplica se ignora (devuelve ``False``). Un evento
        interno fuera de lugar lanza ``TransicionInvalida``.
        """
        siguiente = _TRANSICIONES.get((self.estado, evento))
        if siguiente is None:
            if evento in _DEL_USUARIO:
                return False
            raise TransicionInvalida(f"{evento.name} no es válido en {self.estado.name}")
        anterior, self.estado = self.estado, siguiente
        if self.al_cambiar is not None:
            self.al_cambiar(anterior, siguiente)
        return True
