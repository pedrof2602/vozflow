"""Decide cómo llega un texto a la ventana activa. Lógica pura, sin tocar el escritorio."""

import re
from dataclasses import dataclass

from vozflow.insercion.puerto import AtajoDePegado, Destino
from vozflow.insercion.teclas import (
    CONTROL_IZQUIERDO,
    INSERT,
    LETRA_V,
    MAYUSCULA_IZQUIERDA,
    a_keysym,
    es_escribible,
)

_TECLAS_DE_PEGADO = {
    AtajoDePegado.SHIFT_INSERT: (MAYUSCULA_IZQUIERDA, INSERT),
    AtajoDePegado.CTRL_V: (CONTROL_IZQUIERDO, LETRA_V),
    AtajoDePegado.CTRL_SHIFT_V: (CONTROL_IZQUIERDO, MAYUSCULA_IZQUIERDA, LETRA_V),
}
_SALTOS = re.compile(r"\s*[\r\n]\s*")


@dataclass(frozen=True)
class EstrategiaDePegado:
    texto: str
    atajo: AtajoDePegado
    teclas: tuple[int, ...]
    copiar_a_primaria: bool = True


def decidir_estrategia(texto: str, destino: Destino) -> EstrategiaDePegado:
    """Copiar el texto (portapapeles y selección primaria) y pegar con el atajo del destino.

    Ninguna secuencia lleva Return: un salto de línea viaja dentro del texto pegado o se
    reemplaza por un espacio, nunca como tecla (RF-016).
    """
    if destino.salto_de_linea == "espacio":
        texto = _SALTOS.sub(" ", texto)
    return EstrategiaDePegado(texto, destino.atajo, _TECLAS_DE_PEGADO[destino.atajo])


def teclas_para_escribir(texto: str) -> tuple[int, ...] | None:
    """Keysyms para escribir el texto tecla a tecla, o ``None`` si no se puede sin Enter."""
    if not all(es_escribible(c) for c in texto):
        return None
    return tuple(a_keysym(c) for c in texto)
