"""Comandos de voz (RF-013): «nueva línea», «punto», «coma», «borra eso»…

La tabla de comandos y sus reglas están en ``contracts/comandos-de-voz.md``. Se aplican sobre el
texto ya transcrito, sin modelo de lenguaje.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal

SaltoDeLinea = Literal["conservar", "espacio"]

_PUNTUACION_DEL_MOTOR = ".,;:!?¿¡\"'()[]"
_TERMINADORES = ".!?\n"


@dataclass(frozen=True)
class ResultadoComandos:
    texto: str
    descartar: bool = False


class _Accion(Enum):
    PUNTUACION = auto()
    SALTO = auto()
    PARRAFO = auto()
    ABRE = auto()
    CIERRA = auto()
    BORRAR_TODO = auto()
    BORRAR_ULTIMA_FRASE = auto()


@dataclass(frozen=True)
class _Comando:
    palabras: tuple[str, ...]
    accion: _Accion
    simbolo: str = ""
    invertido: str = ""  # signo de apertura que se agrega al inicio de la oración (español)
    ambigua: bool = False  # una sola palabra que también se usa en el habla normal

    @property
    def es_frase_comun(self) -> bool:
        """Puede aparecer en una oración normal («una nueva línea»); abrir/cerrar/borrar no."""
        return self.accion in (_Accion.PUNTUACION, _Accion.SALTO, _Accion.PARRAFO)


def _c(frase: str, accion: _Accion, simbolo: str = "", *, invertido: str = "") -> _Comando:
    palabras = tuple(frase.split())
    return _Comando(palabras, accion, simbolo, invertido, ambigua=len(palabras) == 1)


_ES = [
    _c("nueva linea", _Accion.SALTO),
    _c("punto y aparte", _Accion.PARRAFO),
    _c("punto y coma", _Accion.PUNTUACION, ";"),
    _c("dos puntos", _Accion.PUNTUACION, ":"),
    _c("punto", _Accion.PUNTUACION, "."),
    _c("coma", _Accion.PUNTUACION, ","),
    _c("signo de interrogacion", _Accion.PUNTUACION, "?", invertido="¿"),
    _c("interrogacion", _Accion.PUNTUACION, "?", invertido="¿"),
    _c("signo de exclamacion", _Accion.PUNTUACION, "!", invertido="¡"),
    _c("exclamacion", _Accion.PUNTUACION, "!", invertido="¡"),
    _c("abre parentesis", _Accion.ABRE, "("),
    _c("cierra parentesis", _Accion.CIERRA, ")"),
    _c("abre comillas", _Accion.ABRE, '"'),
    _c("cierra comillas", _Accion.CIERRA, '"'),
    _c("borra eso", _Accion.BORRAR_TODO),
    _c("borra la ultima frase", _Accion.BORRAR_ULTIMA_FRASE),
]
_EN = [
    _c("new line", _Accion.SALTO),
    _c("new paragraph", _Accion.PARRAFO),
    _c("full stop", _Accion.PUNTUACION, "."),
    _c("period", _Accion.PUNTUACION, "."),
    _c("comma", _Accion.PUNTUACION, ","),
    _c("colon", _Accion.PUNTUACION, ":"),
    _c("semicolon", _Accion.PUNTUACION, ";"),
    _c("question mark", _Accion.PUNTUACION, "?"),
    _c("exclamation mark", _Accion.PUNTUACION, "!"),
    _c("open paren", _Accion.ABRE, "("),
    _c("close paren", _Accion.CIERRA, ")"),
    _c("open quote", _Accion.ABRE, '"'),
    _c("close quote", _Accion.CIERRA, '"'),
    _c("scratch that", _Accion.BORRAR_TODO),
    _c("delete last sentence", _Accion.BORRAR_ULTIMA_FRASE),
]
_TABLAS = {"es": _ES, "en": _EN}

# Si la palabra anterior es una de estas, la frase es parte de una oración normal
# («el punto de control»), no una orden.
_DETERMINANTES = frozenset(
    [
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "este",
        "esta",
        "estos",
        "estas",
        "ese",
        "esa",
        "esos",
        "esas",
        "aquel",
        "aquella",
        "mi",
        "tu",
        "su",
        "mis",
        "tus",
        "sus",
        "nuestro",
        "nuestra",
        "otro",
        "otra",
        "otros",
        "otras",
        "cada",
        "del",
        "al",
        "ningún",
        "ninguna",
        "algún",
        "alguna",
        "cualquier",
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
        "each",
        "every",
        "no",
        "any",
        "some",
    ]
)
# Además, para las palabras sueltas y ambiguas («en punto», «in period»).
_PREPOSICIONES = frozenset(
    [
        "en",
        "por",
        "sin",
        "con",
        "hasta",
        "sobre",
        "entre",
        "desde",
        "hacia",
        "de",
        "para",
        "a",
        "in",
        "on",
        "at",
        "of",
        "to",
        "for",
        "with",
        "by",
        "from",
    ]
)


def _forma(palabra: str) -> str:
    """Minúsculas y sin la puntuación del motor, conservando los acentos (estás ≠ estas)."""
    return palabra.strip(_PUNTUACION_DEL_MOTOR).lower()


def _normalizar(palabra: str) -> str:
    descompuesta = unicodedata.normalize("NFD", _forma(palabra))
    return "".join(c for c in descompuesta if not unicodedata.combining(c))


def _comandos_del_idioma(idioma: str | None) -> list[tuple[str, _Comando]]:
    codigo = (idioma or "").split("-")[0].lower()
    tablas = [codigo] if codigo in _TABLAS else list(_TABLAS)
    comandos = [(t, c) for t in tablas for c in _TABLAS[t]]
    # La frase más larga gana: «punto y aparte» antes que «punto».
    return sorted(comandos, key=lambda par: len(par[1].palabras), reverse=True)


class _Salida:
    """Construye el texto de salida cuidando los espacios alrededor de cada elemento."""

    def __init__(self, salto: SaltoDeLinea) -> None:
        self.texto = ""
        self._sin_espacio = True
        self._salto = salto

    def palabra(self, palabra: str) -> None:
        if not self._sin_espacio and self.texto:
            self.texto += " "
        self.texto += palabra
        self._sin_espacio = False

    def _quitar_espacios_finales(self) -> None:
        self.texto = self.texto.rstrip(" \t")

    def puntuacion(self, simbolo: str, invertido: str) -> None:
        self._quitar_espacios_finales()
        if invertido:
            self._abrir_pregunta_o_exclamacion(invertido)
        if not self.texto.endswith(simbolo):
            self.texto += simbolo
        self._sin_espacio = False

    def _abrir_pregunta_o_exclamacion(self, invertido: str) -> None:
        inicio = max(self.texto.rfind(t) for t in _TERMINADORES) + 1
        oracion = self.texto[inicio:]
        if invertido in oracion:
            return
        # «Hola Pedro, ¿cómo andás?»: el signo va después de la última coma de la oración.
        coma = oracion.rfind(",")
        desde = inicio + (coma + 1 if coma >= 0 else 0)
        resto = self.texto[desde:]
        espacios = len(resto) - len(resto.lstrip(" \t"))
        corte = desde + espacios
        self.texto = self.texto[:corte] + invertido + self.texto[corte:]

    def salto(self) -> None:
        self._quitar_espacios_finales()
        if self._salto == "espacio":
            if self.texto:
                self.texto += " "
            self._sin_espacio = True
            return
        self.texto += "\n"
        self._sin_espacio = True

    def parrafo(self) -> None:
        self._quitar_espacios_finales()
        if self.texto and self.texto[-1] not in ".!?":
            self.texto += "."
        if self._salto == "espacio":
            self.texto += " "
        else:
            self.texto += "\n\n"
        self._sin_espacio = True

    def abre(self, simbolo: str) -> None:
        if self.texto and not self.texto.endswith((" ", "\n")):
            self.texto += " "
        self.texto += simbolo
        self._sin_espacio = True

    def cierra(self, simbolo: str) -> None:
        self._quitar_espacios_finales()
        self.texto += simbolo
        self._sin_espacio = False

    def borrar_ultima_frase(self) -> None:
        texto = self.texto.rstrip()
        buscar_en = texto[:-1] if texto.endswith(tuple(".!?")) else texto
        corte = max(buscar_en.rfind(t) for t in _TERMINADORES) + 1
        self.texto = texto[:corte]
        self._sin_espacio = False


def aplicar_comandos(texto: str, idioma: str | None, salto: SaltoDeLinea) -> ResultadoComandos:
    """Interpreta los comandos de voz del texto.

    ``salto = "espacio"`` es para destinos donde un salto de línea ejecutaría algo (una
    terminal): «nueva línea» y «punto y aparte» insertan un espacio y nunca un salto.
    """
    if salto == "espacio":
        texto = texto.replace("\n", " ")
    palabras = re.findall(r"\n|\S+", texto)
    normalizadas = [_normalizar(p) for p in palabras]
    comandos = _comandos_del_idioma(idioma)
    salida = _Salida(salto)

    i = 0
    while i < len(palabras):
        if palabras[i] == "\n":
            salida.salto()
            i += 1
            continue
        encontrado = next(
            (
                (tabla, comando)
                for tabla, comando in comandos
                if tuple(normalizadas[i : i + len(comando.palabras)]) == comando.palabras
            ),
            None,
        )
        if encontrado is None:
            salida.palabra(palabras[i])
            i += 1
            continue
        tabla, comando = encontrado
        largo = len(comando.palabras)
        anterior = _forma(palabras[i - 1]) if i > 0 else ""
        es_texto_normal = anterior in _DETERMINANTES or (
            comando.ambigua and anterior in _PREPOSICIONES
        )
        if comando.es_frase_comun and es_texto_normal:
            for palabra in palabras[i : i + largo]:
                salida.palabra(palabra)
            i += largo
            continue
        i += largo
        match comando.accion:
            case _Accion.BORRAR_TODO:
                return ResultadoComandos(texto="", descartar=True)
            case _Accion.BORRAR_ULTIMA_FRASE:
                salida.borrar_ultima_frase()
            case _Accion.PUNTUACION:
                salida.puntuacion(comando.simbolo, comando.invertido if tabla == "es" else "")
            case _Accion.SALTO:
                salida.salto()
            case _Accion.PARRAFO:
                salida.parrafo()
            case _Accion.ABRE:
                salida.abre(comando.simbolo)
            case _Accion.CIERRA:
                salida.cierra(comando.simbolo)

    return ResultadoComandos(texto=salida.texto.strip(" \t"))
