"""Copia de seguridad (RF-022): leer, validar y escribir el archivo, sin tocar la base.

El formato está en ``contracts/formato-de-exportacion.md``. La importación es todo o nada: este
módulo valida el archivo entero y, si algo está mal, dice cuál entrada falló.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from vozflow.dominio.claves import normalizar_clave
from vozflow.dominio.modos import SALTOS_DE_LINEA, TIPOS_DE_PEGADO

FORMATO = "vozflow-copia"
VERSION = 1

_MAXIMO_PALABRA = 80
_MAXIMO_DISPARADOR = 100
_BANDERAS = {
    "quitar_muletillas": True,
    "puntuacion_automatica": True,
    "comandos_de_voz": True,
    "reescribir": False,
}


class CopiaInvalida(ValueError):
    """El archivo no sirve; el mensaje dice por qué y, si corresponde, qué entrada falló."""


class VersionNoSoportada(CopiaInvalida):
    """El archivo es de una versión más nueva de la que esta vozflow entiende."""


@dataclass(frozen=True)
class PalabraCopia:
    palabra: str
    nota: str = ""


@dataclass(frozen=True)
class AtajoCopia:
    disparador: str
    reemplazo: str


@dataclass(frozen=True)
class ModoCopia:
    nombre: str
    es_general: bool = False
    quitar_muletillas: bool = True
    puntuacion_automatica: bool = True
    comandos_de_voz: bool = True
    reescribir: bool = False
    instruccion: str = ""
    tipo_pegado: str = "automatico"
    salto_de_linea: str = "conservar"


@dataclass(frozen=True)
class AsignacionCopia:
    aplicacion: str
    modo: str
    es_terminal: bool = False


@dataclass(frozen=True)
class Copia:
    creado_en: str
    diccionario: tuple[PalabraCopia, ...] = ()
    atajos_de_texto: tuple[AtajoCopia, ...] = ()
    modos: tuple[ModoCopia, ...] = ()
    asignaciones: tuple[AsignacionCopia, ...] = ()


# ---- leer ---------------------------------------------------------------------------------------


def interpretar(texto: str) -> Copia:
    try:
        datos = json.loads(texto)
    except ValueError as error:
        raise CopiaInvalida("El archivo no es un JSON válido") from error
    if not isinstance(datos, dict) or datos.get("formato") != FORMATO:
        raise CopiaInvalida(f"El archivo no es una copia de vozflow (falta formato «{FORMATO}»)")
    version = datos.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise CopiaInvalida("El archivo no indica una versión válida")
    if version > VERSION:
        raise VersionNoSoportada(
            f"El archivo es de la versión {version} y esta vozflow entiende hasta la {VERSION}: "
            "actualizá vozflow para importarlo"
        )
    return Copia(
        creado_en=str(datos.get("creado_en", "")),
        diccionario=tuple(_seccion(datos, "diccionario", _palabra)),
        atajos_de_texto=tuple(_seccion(datos, "atajos_de_texto", _atajo)),
        modos=tuple(_seccion(datos, "modos", _modo)),
        asignaciones=tuple(_seccion(datos, "asignaciones", _asignacion)),
    )


def _seccion[T](datos: dict[str, Any], nombre: str, leer: Callable[[dict[str, Any]], T]) -> list[T]:
    entradas = datos.get(nombre, [])
    if not isinstance(entradas, list):
        raise CopiaInvalida(f"{nombre}: tiene que ser una lista")
    resultado: list[T] = []
    for posicion, entrada in enumerate(entradas):
        if not isinstance(entrada, dict):
            raise CopiaInvalida(f"{nombre}[{posicion}]: tiene que ser un objeto")
        try:
            resultado.append(leer(entrada))
        except CopiaInvalida as error:
            raise CopiaInvalida(f"{nombre}[{posicion}]: {error}") from None
    return resultado


def _texto(entrada: dict[str, Any], campo: str, *, obligatorio: bool, defecto: str = "") -> str:
    valor = entrada.get(campo, defecto)
    if not isinstance(valor, str):
        raise CopiaInvalida(f"«{campo}» tiene que ser un texto")
    if obligatorio and not valor.strip():
        raise CopiaInvalida(f"«{campo}» es obligatorio")
    return valor


def _booleano(entrada: dict[str, Any], campo: str, defecto: bool) -> bool:
    valor = entrada.get(campo, defecto)
    if not isinstance(valor, bool):
        raise CopiaInvalida(f"«{campo}» tiene que ser verdadero o falso")
    return valor


def _palabra(entrada: dict[str, Any]) -> PalabraCopia:
    palabra = _texto(entrada, "palabra", obligatorio=True).strip()
    if len(palabra) > _MAXIMO_PALABRA:
        raise CopiaInvalida(f"la palabra no puede pasar de {_MAXIMO_PALABRA} caracteres")
    return PalabraCopia(palabra, _texto(entrada, "nota", obligatorio=False).strip())


def _atajo(entrada: dict[str, Any]) -> AtajoCopia:
    disparador = " ".join(_texto(entrada, "disparador", obligatorio=True).split())
    if len(disparador) > _MAXIMO_DISPARADOR:
        raise CopiaInvalida(f"el disparador no puede pasar de {_MAXIMO_DISPARADOR} caracteres")
    return AtajoCopia(disparador, _texto(entrada, "reemplazo", obligatorio=True))


def _modo(entrada: dict[str, Any]) -> ModoCopia:
    nombre = " ".join(_texto(entrada, "nombre", obligatorio=True).split())
    tipo = _texto(entrada, "tipo_pegado", obligatorio=False, defecto="automatico")
    salto = _texto(entrada, "salto_de_linea", obligatorio=False, defecto="conservar")
    if tipo not in TIPOS_DE_PEGADO:
        raise CopiaInvalida(f"el tipo de pegado tiene que ser uno de {', '.join(TIPOS_DE_PEGADO)}")
    if salto not in SALTOS_DE_LINEA:
        raise CopiaInvalida(f"el salto de línea tiene que ser uno de {', '.join(SALTOS_DE_LINEA)}")
    banderas = {campo: _booleano(entrada, campo, defecto) for campo, defecto in _BANDERAS.items()}
    return ModoCopia(
        nombre=nombre,
        es_general=_booleano(entrada, "es_general", False),
        instruccion=_texto(entrada, "instruccion", obligatorio=False).strip(),
        tipo_pegado=tipo,
        salto_de_linea=salto,
        **banderas,
    )


def _asignacion(entrada: dict[str, Any]) -> AsignacionCopia:
    return AsignacionCopia(
        aplicacion=_texto(entrada, "aplicacion", obligatorio=True).strip().lower(),
        modo=" ".join(_texto(entrada, "modo", obligatorio=True).split()),
        es_terminal=_booleano(entrada, "es_terminal", False),
    )


def validar_asignaciones(copia: Copia, nombres_de_modos: Sequence[str]) -> None:
    """Cada asignación tiene que apuntar a un modo del archivo o a uno que ya existe."""
    conocidos = {normalizar_clave(n) for n in nombres_de_modos}
    conocidos |= {normalizar_clave(m.nombre) for m in copia.modos}
    for posicion, asignacion in enumerate(copia.asignaciones):
        if normalizar_clave(asignacion.modo) not in conocidos:
            raise CopiaInvalida(
                f"asignaciones[{posicion}]: el modo «{asignacion.modo}» no existe"
                " ni está en el archivo"
            )


# ---- escribir ------------------------------------------------------------------------------------


def serializar(copia: Copia) -> str:
    """JSON en UTF-8, con sangría y en un orden que no depende del orden de alta."""
    datos = {
        "formato": FORMATO,
        "version": VERSION,
        "creado_en": copia.creado_en,
        "diccionario": [
            {"palabra": p.palabra, "nota": p.nota}
            for p in sorted(copia.diccionario, key=lambda p: normalizar_clave(p.palabra))
        ],
        "atajos_de_texto": [
            {"disparador": a.disparador, "reemplazo": a.reemplazo}
            for a in sorted(copia.atajos_de_texto, key=lambda a: normalizar_clave(a.disparador))
        ],
        "modos": [
            {
                "nombre": m.nombre,
                "es_general": m.es_general,
                "quitar_muletillas": m.quitar_muletillas,
                "puntuacion_automatica": m.puntuacion_automatica,
                "comandos_de_voz": m.comandos_de_voz,
                "reescribir": m.reescribir,
                "instruccion": m.instruccion,
                "tipo_pegado": m.tipo_pegado,
                "salto_de_linea": m.salto_de_linea,
            }
            for m in sorted(
                copia.modos, key=lambda m: (not m.es_general, normalizar_clave(m.nombre))
            )
        ],
        "asignaciones": [
            {"aplicacion": a.aplicacion, "modo": a.modo, "es_terminal": a.es_terminal}
            for a in sorted(copia.asignaciones, key=lambda a: a.aplicacion)
        ],
    }
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
