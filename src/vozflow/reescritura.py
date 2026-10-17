"""Decide si un dictado se reescribe y con quién, y nunca deja que una falla lo estorbe.

La reescritura es opcional y viene apagada (RF-023). Solo se arma un reescritor —y por lo tanto
solo puede haber una conexión de red— cuando están encendidos el interruptor general, un
proveedor y el modo del dictado. Si algo falla, se devuelve el texto limpio y un aviso (RF-026).
"""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from vozflow.dominio.modos import Modo
from vozflow.dominio.reescritura import Proveedor, armar_instruccion
from vozflow.llm.anthropic import ReescritorAnthropic
from vozflow.llm.ollama import ReescritorOllama
from vozflow.llm.openrouter import ReescritorOpenRouter
from vozflow.llm.puerto import Reescritor, ReescrituraFallida
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.claves import LlaveroNoDisponible
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.proveedores_repo import ProveedoresRepo

_registro = logging.getLogger(__name__)

FabricaDeReescritor = Callable[[Proveedor, str | None], Reescritor]


class LectorDeClaves(Protocol):
    def leer(self, proveedor: str) -> str | None: ...


@dataclass(frozen=True)
class ResultadoReescritura:
    texto: str
    proveedor: str = ""
    """Quién reescribió; vacío si el texto quedó como estaba."""
    aviso: str | None = None


def crear_reescritor(proveedor: Proveedor, clave: str | None) -> Reescritor:
    if proveedor.id == "ollama":
        return ReescritorOllama(proveedor.modelo, proveedor.direccion)
    assert clave is not None
    if proveedor.id == "anthropic":
        return ReescritorAnthropic(proveedor.modelo, clave)
    return ReescritorOpenRouter(proveedor.modelo, clave)


class ReescrituraDeBase:
    """Lee la configuración en cada dictado, así un cambio rige enseguida."""

    def __init__(
        self,
        base: sqlite3.Connection,
        claves: LectorDeClaves,
        crear: FabricaDeReescritor = crear_reescritor,
    ) -> None:
        self._ajustes = AjustesRepo(base)
        self._proveedores = ProveedoresRepo(base)
        self._diccionario = DiccionarioRepo(base)
        self._claves = claves
        self._crear = crear

    def intentar(self, texto: str, modo: Modo) -> ResultadoReescritura:
        if not modo.reescribir or not self._ajustes.obtener("reescritura.activa"):
            return ResultadoReescritura(texto)  # nada que hacer: ni siquiera se prepara un cliente
        proveedor = self._proveedores.activo()
        if proveedor is None:
            return self._sin_cambios(texto, "La reescritura está activada pero no hay un proveedor")
        try:
            clave = self._clave_de(proveedor)
        except (LlaveroNoDisponible, ValueError) as error:
            return self._sin_cambios(texto, str(error))
        if clave is None and proveedor.id != "ollama":
            return self._sin_cambios(
                texto, f"Falta la clave de {proveedor.id}: guardala con «proveedor clave»"
            )
        try:
            reescritor = self._crear(proveedor, clave)
            palabras = [e.palabra for e in self._diccionario.listar()]
            instruccion = armar_instruccion(modo, palabras)
            reescrito = reescritor.reescribir(texto, instruccion, proveedor.tiempo_maximo_s)
        except ReescrituraFallida as error:
            return self._sin_cambios(texto, str(error))
        except Exception:
            _registro.exception("Falló la reescritura de forma inesperada")
            return self._sin_cambios(texto, "La reescritura falló")
        return ResultadoReescritura(reescrito, proveedor.id)

    def _clave_de(self, proveedor: Proveedor) -> str | None:
        return None if proveedor.id == "ollama" else self._claves.leer(proveedor.id)

    @staticmethod
    def _sin_cambios(texto: str, motivo: str) -> ResultadoReescritura:
        return ResultadoReescritura(texto, aviso=f"{motivo}. Se insertó el texto sin reescribir.")
