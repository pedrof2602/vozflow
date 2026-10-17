"""La administración de proveedores de reescritura que comparten la consola y la ventana.

Reúne lo que hay que respetar al configurar: un modelo elegido, la clave en el llavero, uno solo
activo y el interruptor general. Los mensajes de error se pueden mostrar tal cual: nunca llevan la
clave.
"""

import sqlite3
from dataclasses import dataclass
from typing import Protocol

from vozflow.dominio.reescritura import Proveedor
from vozflow.llm.puerto import ReescrituraFallida
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.proveedores_repo import ProveedoresRepo
from vozflow.reescritura import FabricaDeReescritor

_TEXTO_DE_PRUEBA = "hola mundo esto es una prueba"
_INSTRUCCION_DE_PRUEBA = "Corregí la puntuación y las mayúsculas. Devolvé solo el texto."


class ErrorDeProveedor(Exception):
    """No se pudo cumplir la orden; el mensaje se puede mostrar tal cual."""


class AlmacenDeClaves(Protocol):
    def guardar(self, proveedor: str, clave: str) -> None: ...
    def leer(self, proveedor: str) -> str | None: ...
    def existe(self, proveedor: str) -> bool: ...
    def borrar(self, proveedor: str) -> bool: ...


@dataclass(frozen=True)
class EstadoDeProveedor:
    proveedor: Proveedor
    tiene_clave: bool | None
    """``None`` para Ollama, que no usa clave."""


class GestionDeProveedores:
    def __init__(
        self,
        base: sqlite3.Connection,
        claves: AlmacenDeClaves,
        crear_reescritor: FabricaDeReescritor,
    ) -> None:
        self._proveedores = ProveedoresRepo(base)
        self._ajustes = AjustesRepo(base)
        self._claves = claves
        self._crear = crear_reescritor

    # ---- consultar -------------------------------------------------------------------------------

    def reescritura_encendida(self) -> bool:
        return bool(self._ajustes.obtener("reescritura.activa"))

    def idioma_de_traduccion(self) -> str:
        return str(self._ajustes.obtener("traduccion.idioma"))

    def proveedor_activo(self) -> Proveedor | None:
        return self._proveedores.activo()

    def estado(self) -> list[EstadoDeProveedor]:
        return [
            EstadoDeProveedor(p, None if p.id == "ollama" else self._claves.existe(p.id))
            for p in self._proveedores.listar()
        ]

    # ---- cambiar ---------------------------------------------------------------------------------

    def configurar(
        self,
        id_: str,
        *,
        modelo: str | None = None,
        direccion: str | None = None,
        tiempo_maximo_s: int | None = None,
    ) -> None:
        try:
            self._proveedores.configurar(
                id_, modelo=modelo, direccion=direccion, tiempo_maximo_s=tiempo_maximo_s
            )
        except DatoInvalido as error:
            raise ErrorDeProveedor(str(error)) from None

    def establecer_idioma_de_traduccion(self, idioma: str) -> None:
        try:
            self._ajustes.establecer("traduccion.idioma", idioma)
        except DatoInvalido as error:
            raise ErrorDeProveedor(str(error)) from None

    def guardar_clave(self, id_: str, clave: str) -> None:
        try:
            self._claves.guardar(id_, clave)
        except DatoInvalido as error:
            raise ErrorDeProveedor(str(error)) from None

    def borrar_clave(self, id_: str) -> None:
        if not self._claves.borrar(id_):
            raise ErrorDeProveedor(f"No había una clave de {id_} guardada")

    def activar(self, id_: str) -> None:
        """Enciende la reescritura con ``id_``: exige modelo y, si no es local, la clave."""
        self._clave_lista(self._obtener(id_))
        try:
            self._proveedores.activar(id_)
        except DatoInvalido as error:
            raise ErrorDeProveedor(str(error)) from None
        self._ajustes.establecer("reescritura.activa", True)

    def desactivar(self) -> None:
        self._proveedores.desactivar()
        self._ajustes.establecer("reescritura.activa", False)

    def probar(self, id_: str | None) -> str:
        """Manda un texto de ejemplo y devuelve la respuesta (o lanza ``ErrorDeProveedor``)."""
        proveedor = self._obtener(id_) if id_ else self._proveedores.activo()
        if proveedor is None:
            raise ErrorDeProveedor("Indicá un proveedor o activá uno")
        clave = self._clave_lista(proveedor)
        reescritor = self._crear(proveedor, clave)
        try:
            return reescritor.reescribir(
                _TEXTO_DE_PRUEBA, _INSTRUCCION_DE_PRUEBA, proveedor.tiempo_maximo_s
            )
        except ReescrituraFallida as error:
            raise ErrorDeProveedor(str(error)) from None

    # ---- internos --------------------------------------------------------------------------------

    def _obtener(self, id_: str) -> Proveedor:
        try:
            return self._proveedores.obtener(id_)
        except DatoInvalido as error:
            raise ErrorDeProveedor(str(error)) from None

    def _clave_lista(self, proveedor: Proveedor) -> str | None:
        """Comprueba que se pueda usar y devuelve su clave (``None`` para Ollama)."""
        if not proveedor.modelo:
            raise ErrorDeProveedor(f"Elegí un modelo para {proveedor.id} antes de usarlo")
        if proveedor.id == "ollama":
            return None
        clave = self._claves.leer(proveedor.id)
        if not clave:
            raise ErrorDeProveedor(f"Falta la clave de {proveedor.id}: guardala primero")
        return clave
