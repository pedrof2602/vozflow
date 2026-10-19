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
    fallo: bool = False
    """Se pidió reescribir o traducir y no se pudo. Reescribir tolera el fallo (se inserta el
    texto limpio); traducir no: saldría en el idioma equivocado."""


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

    def intentar(
        self, texto: str, modo: Modo, traducir_a: str | None = None
    ) -> ResultadoReescritura:
        """Mejora el texto (tecla de mejorar) o lo mejora y traduce (tecla de traducir).

        Solo se llama cuando la persona pidió IA con una de esas teclas: dictar a secas nunca llega
        acá (003). El interruptor ``modo.reescribir`` ya no decide nada.
        """
        traduciendo = traducir_a is not None
        if not self._ajustes.obtener("reescritura.activa"):
            return self._sin_cambios(
                texto,
                "El asistente de IA está apagado (Ajustes → Avanzado → Asistente de IA)",
                traduciendo=traduciendo,
            )
        proveedor = self._proveedores.activo()
        if proveedor is None:
            return self._sin_cambios(
                texto,
                "El asistente de IA está prendido pero no hay un proveedor elegido",
                traduciendo=traduciendo,
            )
        try:
            clave = self._clave_de(proveedor)
        except (LlaveroNoDisponible, ValueError) as error:
            return self._sin_cambios(texto, str(error), traduciendo=traduciendo)
        if clave is None and proveedor.id != "ollama":
            return self._sin_cambios(
                texto,
                f"Falta la clave de {proveedor.id}: guardala con «proveedor clave»",
                traduciendo=traduciendo,
            )
        try:
            reescritor = self._crear(proveedor, clave)
            palabras = [e.palabra for e in self._diccionario.listar()]
            instruccion = armar_instruccion(modo, palabras, traducir_a)
            reescrito = reescritor.reescribir(texto, instruccion, proveedor.tiempo_maximo_s)
        except ReescrituraFallida as error:
            return self._sin_cambios(texto, str(error), traduciendo=traduciendo)
        except Exception:
            _registro.exception("Falló la reescritura de forma inesperada")
            return self._sin_cambios(
                texto, "La traducción falló" if traduciendo else "La mejora falló",
                traduciendo=traduciendo,
            )  # fmt: skip
        return ResultadoReescritura(reescrito, proveedor.id)

    def _clave_de(self, proveedor: Proveedor) -> str | None:
        return None if proveedor.id == "ollama" else self._claves.leer(proveedor.id)

    @staticmethod
    def _sin_cambios(texto: str, motivo: str, *, traduciendo: bool) -> ResultadoReescritura:
        _registro.warning(
            "El asistente de IA no pudo %s: %s", "traducir" if traduciendo else "mejorar", motivo
        )
        if traduciendo:
            return ResultadoReescritura(
                texto,
                aviso=(
                    f"No se pudo traducir: {motivo}. No se insertó nada; "
                    "el texto quedó en el historial."
                ),
                fallo=True,
            )
        return ResultadoReescritura(
            texto, aviso=f"{motivo}. Se insertó el texto sin mejorar.", fallo=True
        )
