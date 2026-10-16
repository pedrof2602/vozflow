"""Teclas por keysym, independientes de la distribución del teclado.

Un keysym identifica el *carácter o la tecla*, no la posición física: por eso «ñ» sale bien con el
teclado ``latam`` de Pedro, algo que ``ydotool type`` (pensado para teclado de EE. UU.) no logra.
"""

CONTROL_IZQUIERDO = 0xFFE3
MAYUSCULA_IZQUIERDA = 0xFFE1
INSERT = 0xFF63
RETURN = 0xFF0D
LETRA_V = 0x76
LETRA_C = 0x63

_BASE_UNICODE = 0x01000000


def es_escribible(caracter: str) -> bool:
    """Falso para saltos de línea, tabuladores y demás caracteres de control.

    Un salto de línea escrito como tecla sería un Enter, y en una terminal ejecutaría el comando
    (RF-016). Esos caracteres nunca se convierten en teclas.
    """
    codigo = ord(caracter)
    return not (codigo < 0x20 or 0x7F <= codigo < 0xA0)


def a_keysym(caracter: str) -> int:
    """Keysym de un carácter: su punto de código en Latin-1, o la regla Unicode del resto."""
    if len(caracter) != 1:
        raise ValueError("Se esperaba un solo carácter")
    if not es_escribible(caracter):
        raise ValueError(f"El carácter {caracter!r} no se escribe por teclas")
    codigo = ord(caracter)
    return codigo if codigo <= 0xFF else _BASE_UNICODE + codigo
