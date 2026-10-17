"""De dónde saca ``Aplicacion`` lo que la persona configuró: diccionario, atajos y modos.

Se lee en cada dictado, así un cambio rige enseguida sin reiniciar el servicio.
"""

import sqlite3
from collections.abc import Callable, Collection, Sequence
from dataclasses import replace
from typing import Protocol

from vozflow.dominio.atajos_texto import AtajoTexto
from vozflow.dominio.diccionario import construir_pista
from vozflow.dominio.modos import Asignacion, Modo, Resolucion, resolver
from vozflow.dominio.tuberia import OPCIONES_POR_DEFECTO, OpcionesDeTuberia
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.modos_repo import ModosRepo


class FuenteDeConfiguracion(Protocol):
    def pista(self) -> str | None:
        """Las palabras del diccionario como pista para el motor."""
        ...

    def resolver(self, aplicacion: str | None) -> Resolucion:
        """El modo, las opciones de texto (con los atajos) y el destino de la aplicación."""
        ...

    def idioma_de_traduccion(self) -> str:
        """El idioma al que traduce la tecla de traducir."""
        ...


class ConfiguracionEstatica:
    """Sin base de datos: un solo modo general y, si se quiere, una pista y terminales marcadas."""

    def __init__(
        self,
        opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO,
        terminales: Collection[str] = (),
        pista: Callable[[], str | None] | None = None,
        idioma_de_traduccion: str = "inglés",
    ) -> None:
        self._idioma_de_traduccion = idioma_de_traduccion
        self._opciones = opciones
        self._terminales = frozenset(terminales)
        self._pista = pista

    def pista(self) -> str | None:
        return self._pista() if self._pista is not None else None

    def idioma_de_traduccion(self) -> str:
        return self._idioma_de_traduccion

    def resolver(self, aplicacion: str | None) -> Resolucion:
        general = Modo(
            1,
            "General",
            es_general=True,
            quitar_muletillas=self._opciones.quitar_muletillas,
            puntuacion_automatica=self._opciones.puntuacion_automatica,
            comandos_de_voz=self._opciones.comandos_de_voz,
            salto_de_linea=self._opciones.salto_de_linea,
        )
        asignaciones = [Asignacion(a, 1, es_terminal=True) for a in self._terminales]
        resolucion = resolver(aplicacion, asignaciones, [general])
        return replace(
            resolucion, opciones=replace(resolucion.opciones, atajos=self._opciones.atajos)
        )


class ConfiguracionDeBase:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._ajustes = AjustesRepo(base)
        self._diccionario = DiccionarioRepo(base)
        self._atajos = AtajosTextoRepo(base)
        self._modos = ModosRepo(base)
        self._asignaciones = AsignacionesRepo(base)

    def pista(self) -> str | None:
        return construir_pista([e.palabra for e in self._diccionario.listar()])

    def idioma_de_traduccion(self) -> str:
        return str(self._ajustes.obtener("traduccion.idioma"))

    def atajos_de_texto(self) -> Sequence[AtajoTexto]:
        return self._atajos.listar()

    def resolver(self, aplicacion: str | None) -> Resolucion:
        resolucion = resolver(aplicacion, self._asignaciones.listar(), self._modos.listar())
        opciones = replace(resolucion.opciones, atajos=tuple(self.atajos_de_texto()))
        return replace(resolucion, opciones=opciones)
