"""Comparar textos del usuario sin distinguir mayúsculas, acentos ni espacios repetidos."""

import unicodedata


def _plano(caracter: str) -> str:
    base = "".join(
        c for c in unicodedata.normalize("NFD", caracter) if not unicodedata.combining(c)
    )
    minuscula = (base or caracter).lower()
    return minuscula if len(minuscula) == 1 else caracter


def plano_alineado(texto: str) -> str:
    """El texto sin mayúsculas ni acentos, con **un carácter por cada carácter original**.

    Sirve para buscar sobre el texto normalizado y volver a las posiciones del original.
    """
    return "".join(_plano(c) for c in texto)


def normalizar_clave(texto: str) -> str:
    """La forma con la que se decide si dos entradas son la misma."""
    return " ".join(plano_alineado(texto).split())
