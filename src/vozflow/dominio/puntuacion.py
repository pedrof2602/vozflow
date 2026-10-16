"""Puntuación y mayúsculas del texto dictado (RF-011).

Whisper ya devuelve puntuación en la mayoría de los casos. Esto corrige lo que suele fallar
—espacios, mayúsculas tras un punto, signos invertidos en español, el punto final— sin tocar
nombres de archivo, números ni direcciones.
"""

import re

_LETRAS = "a-záéíóúüñ"
# Una palabra «pura» (sin puntos, barras ni guiones bajos intermedios) puede capitalizarse.
_PALABRA_PURA = re.compile(rf"^[{_LETRAS}][{_LETRAS}'’-]*[,;:)\"'’]*$")
_TERMINADOR = re.compile(r"[.!?]+(?=\s|$)")
_CARACTERES_DE_RUTA = re.compile(r"[/\\_@=.:#]")
_APERTURAS = "¿¡\"'(["


def _es_espanol(idioma: str | None) -> bool:
    return (idioma or "").split("-")[0].lower() == "es"


def _ajustar_espacios(linea: str) -> str:
    linea = re.sub(r"[ \t]+", " ", linea).strip()
    linea = re.sub(r"\s+([,.;:?!)])", r"\1", linea)
    # Falta el espacio tras una coma o punto y coma: «hola,mundo».
    linea = re.sub(r"([,;])(?=[^\s\d,.;:?!)\"'’\]])", r"\1 ", linea)
    # Falta el espacio entre dos oraciones pegadas: «Hola.Mundo».
    return re.sub(rf"(?<=[{_LETRAS}])([.?!])(?=[A-ZÁÉÍÓÚÜÑ¿¡])", r"\1 ", linea)


def _dividir_en_oraciones(linea: str) -> list[str]:
    """Parte la línea tras cada terminador seguido de espacio o fin de texto."""
    oraciones: list[str] = []
    inicio = 0
    for terminador in _TERMINADOR.finditer(linea):
        oraciones.append(linea[inicio : terminador.end()])
        inicio = terminador.end()
    if inicio < len(linea):
        oraciones.append(linea[inicio:])
    return oraciones


def _terminador_de(oracion: str) -> str:
    coincidencia = re.search(r"[.!?]+$", oracion)
    return coincidencia.group(0) if coincidencia else ""


def _agregar_signo_invertido(oracion: str, terminador: str) -> str:
    """«hola, cómo estás?» → «hola, ¿cómo estás?»: el signo va tras la última coma."""
    if not terminador or terminador[0] not in "?!":
        return oracion
    invertido = "¿" if terminador[0] == "?" else "¡"
    cuerpo = oracion[: len(oracion) - len(terminador)]
    if invertido in cuerpo or not re.search(r"\w", cuerpo):
        return oracion
    # Una coma entre dígitos es decimal («1,5»), no una pausa.
    comas = [m.start() for m in re.finditer(r"(?<!\d),|,(?!\d)", cuerpo)]
    coma = comas[-1] if comas else -1
    # Solo vale «tras la última coma» si después de ella hay texto; si no, desde el inicio.
    desde = coma + 1 if coma >= 0 and cuerpo[coma + 1 :].strip() else 0
    resto = cuerpo[desde:]
    corte = desde + len(resto) - len(resto.lstrip(" "))
    # Tras una coma el signo va separado por un espacio; se agrega ya en esta pasada.
    marca = " " + invertido if desde > 0 and corte == desde else invertido
    return oracion[:corte] + marca + oracion[corte:]


def _capitalizar(oracion: str) -> str:
    coincidencia = re.match(rf"^(\s*[{re.escape(_APERTURAS)}]*)(\S+)", oracion)
    if coincidencia is None:
        return oracion
    prefijo, palabra = coincidencia.groups()
    if not _PALABRA_PURA.match(palabra.rstrip(".!?")):
        return oracion
    return prefijo + palabra[0].upper() + palabra[1:] + oracion[coincidencia.end() :]


def _es_puntos_suspensivos(terminador: str) -> bool:
    return len(terminador) >= 3 and set(terminador) == {"."}


def _normalizar_linea(linea: str, espanol: bool) -> str:
    oraciones = _dividir_en_oraciones(_ajustar_espacios(linea))
    resultado: list[str] = []
    empieza_oracion = True
    for oracion in oraciones:
        terminador = _terminador_de(oracion)
        if espanol:
            oracion = _agregar_signo_invertido(oracion, terminador)
        if empieza_oracion:
            oracion = _capitalizar(oracion)
        resultado.append(oracion)
        # Tras unos puntos suspensivos la frase suele continuar en minúscula.
        empieza_oracion = bool(terminador) and not _es_puntos_suspensivos(terminador)
    return "".join(resultado)


def _agregar_punto_final(linea: str) -> str:
    palabras = linea.split()
    if len(palabras) < 2 or not re.search(r"\w$", linea):
        return linea
    if _CARACTERES_DE_RUTA.search(palabras[-1]):
        return linea
    return linea + "."


def normalizar_puntuacion(texto: str, idioma: str | None) -> str:
    """Espacios, mayúsculas, signos invertidos (solo en español) y punto final.

    El punto final se agrega solo a la última línea y a frases de dos o más palabras, para no
    llenar de puntos una lista dictada línea por línea ni una respuesta de una palabra.
    """
    espanol = _es_espanol(idioma)
    lineas = [_normalizar_linea(linea, espanol) for linea in texto.split("\n")]
    for indice in range(len(lineas) - 1, -1, -1):
        if lineas[indice]:
            lineas[indice] = _agregar_punto_final(lineas[indice])
            break
    return "\n".join(lineas)
