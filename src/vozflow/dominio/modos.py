"""Modos por aplicación (RF-021): qué reglas y qué pegado usa cada aplicación."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from vozflow.dominio.claves import normalizar_clave
from vozflow.dominio.comandos_voz import SaltoDeLinea
from vozflow.dominio.terminales import es_terminal
from vozflow.dominio.tuberia import OpcionesDeTuberia
from vozflow.insercion.puerto import AtajoDePegado, Destino

TipoDePegado = Literal["normal", "terminal", "automatico"]
TIPOS_DE_PEGADO: tuple[str, ...] = ("normal", "terminal", "automatico")
SALTOS_DE_LINEA: tuple[str, ...] = ("conservar", "espacio")


@dataclass(frozen=True)
class Modo:
    id: int
    nombre: str
    es_general: bool = False
    quitar_muletillas: bool = True
    puntuacion_automatica: bool = True
    comandos_de_voz: bool = True
    reescribir: bool = False
    instruccion: str = ""
    tipo_pegado: TipoDePegado = "automatico"
    salto_de_linea: SaltoDeLinea = "conservar"


@dataclass(frozen=True)
class Asignacion:
    aplicacion: str
    modo_id: int
    es_terminal: bool = False


@dataclass(frozen=True)
class Resolucion:
    modo: Modo
    es_terminal: bool
    opciones: OpcionesDeTuberia
    destino: Destino


def resolver(
    aplicacion: str | None, asignaciones: Sequence[Asignacion], modos: Sequence[Modo]
) -> Resolucion:
    """El modo de ``aplicacion``: el asignado o, si no hay fila, el general."""
    general = next((m for m in modos if m.es_general), None)
    if general is None:
        raise LookupError("No hay un modo general")
    clave = normalizar_clave(aplicacion or "")
    asignacion = next((a for a in asignaciones if normalizar_clave(a.aplicacion) == clave), None)
    modo = general
    if asignacion is not None:
        modo = next((m for m in modos if m.id == asignacion.modo_id), general)
    marcadas = {clave} if asignacion is not None and asignacion.es_terminal else set()
    terminal = modo.tipo_pegado == "terminal" or (
        modo.tipo_pegado == "automatico" and es_terminal(clave, marcadas)
    )
    # Una terminal nunca recibe saltos de línea: ejecutarían lo pegado (RF-016).
    salto: SaltoDeLinea = "espacio" if terminal else modo.salto_de_linea
    destino = Destino(
        atajo=AtajoDePegado.CTRL_SHIFT_V if terminal else AtajoDePegado.SHIFT_INSERT,
        salto_de_linea=salto,
    )
    opciones = OpcionesDeTuberia(
        quitar_muletillas=modo.quitar_muletillas,
        puntuacion_automatica=modo.puntuacion_automatica,
        comandos_de_voz=modo.comandos_de_voz,
        salto_de_linea=salto,
    )
    return Resolucion(modo, terminal, opciones, destino)
