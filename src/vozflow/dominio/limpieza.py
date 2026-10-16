"""Limpieza del texto dictado: muletillas y repeticiones (RF-012).

Reglas simples y conservadoras, sin modelo de lenguaje. Se aplican línea por línea porque
los comandos de voz pueden haber dejado saltos de línea que hay que conservar.
"""

import re

LARGO_MAXIMO_DE_REPETICION = 4
_VUELTAS_MAXIMAS = 20

# Sonidos que nunca son parte de una frase. «mm» no se quita si va tras un número (5 mm).
_SONIDOS = re.compile(
    r"\s*(?<!\w)(?:eh+m*|ehm+|em+|(?<!\d)(?<!\d\s)mm+h?|uh+|um+|hm+)(?!\w),?",
    re.IGNORECASE,
)

# Palabras que son muletilla solo si van entre pausas; si no, son parte de la frase.
_MULETILLAS = {
    "es": ("este", "o sea", "bueno"),
    "en": ("you know", "i mean", "like"),
}

# Palabras funcionales que, repetidas, casi seguro son un titubeo («el el», «que que»).
_FUNCIONALES = [
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "de",
    "del",
    "al",
    "en",
    "y",
    "e",
    "o",
    "u",
    "a",
    "que",
    "se",
    "lo",
    "le",
    "les",
    "me",
    "te",
    "mi",
    "tu",
    "su",
    "con",
    "por",
    "para",
    "yo",
    "tú",
    "él",
    "ella",
    "es",
    "son",
    "fue",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "and",
    "or",
    "i",
    "it",
    "is",
    "we",
    "you",
    "they",
    "he",
    "she",
]
_REPETICION_FUNCIONAL = re.compile(
    r"(?<!\w)(" + "|".join(sorted(map(re.escape, _FUNCIONALES), key=len, reverse=True)) + r")"
    r"(?:,?[ \t]+)\1(?!\w)",
    re.IGNORECASE,
)
_REPETICIONES_DE_FRASE = [
    re.compile(
        r"(?<!\w)((?:\w+[ \t]+){" + str(n - 1) + r"}\w+)(?:,?[ \t]+)\1(?!\w)",
        re.IGNORECASE,
    )
    for n in range(LARGO_MAXIMO_DE_REPETICION, 1, -1)
]


def _expresiones_de_muletillas(idioma: str | None) -> list[tuple[re.Pattern[str], str]]:
    codigo = (idioma or "").split("-")[0].lower()
    listas = [_MULETILLAS[codigo]] if codigo in _MULETILLAS else list(_MULETILLAS.values())
    palabras = "|".join(re.escape(p) for lista in listas for p in lista)
    return [
        # Al inicio del texto o de una oración: «Este, ahora sigo».
        (re.compile(rf"(?:^|(?<=[.!?] ))(?:{palabras})(?:,[ \t]*)", re.IGNORECASE), ""),
        # Entre dos pausas: «primero, este, vamos».
        (re.compile(rf",[ \t]*(?:{palabras}),", re.IGNORECASE), ","),
        # Al final: «necesito el archivo, o sea.».
        (re.compile(rf",[ \t]*(?:{palabras})(?=[ \t]*[.!?]*[ \t]*$)", re.IGNORECASE), ""),
    ]


def _ordenar(linea: str) -> str:
    """Normaliza espacios y comas sueltas que deja la eliminación."""
    linea = re.sub(r"[ \t]+", " ", linea)
    linea = re.sub(r"\s+([,.;:?!])", r"\1", linea)
    linea = re.sub(r",(?:\s*,)+", ",", linea)
    linea = re.sub(r",\s*([.!?])", r"\1", linea)
    linea = re.sub(r"^[\s,]+", "", linea)
    linea = re.sub(r"[\s,]+$", "", linea)
    return linea.strip()


def _una_vuelta(linea: str, muletillas: list[tuple[re.Pattern[str], str]]) -> str:
    linea = _SONIDOS.sub("", linea)
    for expresion, reemplazo in muletillas:
        linea = expresion.sub(reemplazo, linea)
    for expresion in _REPETICIONES_DE_FRASE:
        linea = expresion.sub(r"\1", linea)
    linea = _REPETICION_FUNCIONAL.sub(r"\1", linea)
    return _ordenar(linea)


def _limpiar_linea(linea: str, muletillas: list[tuple[re.Pattern[str], str]]) -> str:
    for _ in range(_VUELTAS_MAXIMAS):
        siguiente = _una_vuelta(linea, muletillas)
        if siguiente == linea:
            break
        linea = siguiente
    return linea


def limpiar(texto: str, idioma: str | None) -> str:
    """Quita muletillas y repeticiones inmediatas; conserva los saltos de línea."""
    muletillas = _expresiones_de_muletillas(idioma)
    return "\n".join(_limpiar_linea(linea, muletillas) for linea in texto.split("\n"))
