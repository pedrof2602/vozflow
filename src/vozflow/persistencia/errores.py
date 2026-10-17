"""Errores de validación de los datos del usuario; los mensajes se pueden mostrar tal cual."""


class DatoInvalido(ValueError):
    """Un dato no cumple las reglas de ``data-model.md``."""


class DatoDuplicado(DatoInvalido):
    """Ya existe algo igual (sin distinguir mayúsculas, acentos ni espacios repetidos)."""
