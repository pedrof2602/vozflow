"""Contrato de la escucha de atajos (contracts/puertos.md, RF-001 a RF-004).

Hay cuatro acciones: ``mantener`` (hablar mientras se aprieta la tecla), ``mejorar`` (igual, pero el
texto lo pule el asistente de IA), ``traducir`` (igual, pero se pule y se traduce) y ``alternar``
(una pulsación empieza y otra termina). Cada técnica del
sistema —el atajo de GNOME, ``evdev``, el portal— traduce lo que ve a ``pulsado`` y ``soltado``
y se lo pasa a un ``Despachador``, que aplica las mismas reglas para todas.
"""

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

_registro = logging.getLogger(__name__)


class AccionDeAtajo(StrEnum):
    MANTENER = "mantener"
    ALTERNAR = "alternar"
    TRADUCIR = "traducir"
    MEJORAR = "mejorar"


class FaseDeAtajo(StrEnum):
    PULSADO = "pulsado"
    SOLTADO = "soltado"


@dataclass(frozen=True)
class EventoDeAtajo:
    accion: AccionDeAtajo
    fase: FaseDeAtajo


class AtajoOcupado(Exception):
    """La combinación de teclas ya la usa otra función del escritorio (RF-003)."""


AlEvento = Callable[[EventoDeAtajo], None]


class EscuchaDeAtajos(Protocol):
    def iniciar(self, atajos: Mapping[AccionDeAtajo, str], al_evento: AlEvento) -> None:
        """Empieza a escuchar. Lanza ``AtajoOcupado`` si una combinación ya está en uso y
        ``RuntimeError`` si ya estaba iniciada. ``al_evento`` se llama desde un hilo propio."""

    def detener(self) -> None:
        """Deja de escuchar. Es inofensivo si no estaba iniciada o si se repite."""


class FiltroDeRepeticion:
    """Quita las repeticiones de una tecla mantenida y los ``soltado`` que no corresponden.

    - ``mantener`` y ``traducir``: pasan ``pulsado`` y el ``soltado`` que le sigue; todo lo demás
      se ignora.
    - ``alternar``: pasa un ``pulsado`` por cada pulsación; el ``soltado`` nunca pasa.
    """

    def __init__(self) -> None:
        self._apretadas: set[AccionDeAtajo] = set()

    def permitir(self, evento: EventoDeAtajo) -> bool:
        apretada = evento.accion in self._apretadas
        if evento.fase is FaseDeAtajo.PULSADO:
            if apretada:
                return False
            self._apretadas.add(evento.accion)
            return True
        if not apretada:
            return False
        self._apretadas.discard(evento.accion)
        return evento.accion is not AccionDeAtajo.ALTERNAR

    def reiniciar(self) -> None:
        self._apretadas.clear()


class Despachador:
    """Entrega los eventos ya filtrados, y no deja que un error de quien los recibe mate la escucha.

    Es seguro llamarlo desde varios hilos.
    """

    def __init__(self, al_evento: AlEvento) -> None:
        self._al_evento = al_evento
        self._filtro = FiltroDeRepeticion()
        self._candado = threading.Lock()
        self._activo = True

    @property
    def activo(self) -> bool:
        return self._activo

    def emitir(self, accion: AccionDeAtajo, fase: FaseDeAtajo) -> None:
        evento = EventoDeAtajo(accion, fase)
        with self._candado:
            if not self._activo or not self._filtro.permitir(evento):
                return
        try:
            self._al_evento(evento)
        except Exception:
            _registro.exception("Falló quien recibe el evento de atajo %s", evento)

    def detener(self) -> None:
        with self._candado:
            self._activo = False
            self._filtro.reiniciar()

    def reanudar(self) -> None:
        with self._candado:
            self._activo = True
            self._filtro.reiniciar()
