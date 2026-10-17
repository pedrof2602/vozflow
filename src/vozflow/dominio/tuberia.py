"""Tubería de texto: comandos de voz → limpieza → puntuación → atajos de texto.

El orden importa: un comando como «coma» tiene que convertirse en «,» antes de que la limpieza
vea la repetición «tengo que, tengo que», y las mayúsculas se ponen al final, cuando ya no
quedan muletillas que puedan ocupar el inicio de la oración.
"""

from dataclasses import dataclass

from vozflow.dominio.atajos_texto import AtajoTexto, expandir
from vozflow.dominio.comandos_voz import SaltoDeLinea, aplicar_comandos
from vozflow.dominio.limpieza import limpiar
from vozflow.dominio.puntuacion import normalizar_puntuacion


@dataclass(frozen=True)
class OpcionesDeTuberia:
    """Banderas de un modo (data-model.md, «Modo»)."""

    quitar_muletillas: bool = True
    puntuacion_automatica: bool = True
    comandos_de_voz: bool = True
    salto_de_linea: SaltoDeLinea = "conservar"
    atajos: tuple[AtajoTexto, ...] = ()


OPCIONES_POR_DEFECTO = OpcionesDeTuberia()


@dataclass(frozen=True)
class ResultadoProceso:
    texto: str
    descartar: bool = False


def procesar(
    texto: str, idioma: str | None, opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO
) -> ResultadoProceso:
    """Aplica los pasos activos. Con todo apagado devuelve el texto sin tocarlo."""
    if opciones.comandos_de_voz:
        comandos = aplicar_comandos(texto, idioma, opciones.salto_de_linea)
        if comandos.descartar:
            return ResultadoProceso(texto="", descartar=True)
        texto = comandos.texto
    if opciones.quitar_muletillas:
        texto = limpiar(texto, idioma)
    if opciones.puntuacion_automatica:
        texto = normalizar_puntuacion(texto, idioma)
    if opciones.atajos:
        # Al final, para que el reemplazo llegue tal cual lo escribió la persona.
        texto = expandir(texto, opciones.atajos)
    if opciones.salto_de_linea == "espacio":
        # Un destino que ejecutaría el texto (una terminal) nunca recibe un salto de línea.
        texto = texto.replace("\n", " ")
    return ResultadoProceso(texto=texto)
