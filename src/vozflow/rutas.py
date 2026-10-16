"""Rutas de datos, caché y configuración, según la especificación XDG."""

import os
from pathlib import Path

_NOMBRE = "vozflow"


def _directorio_xdg(variable: str, por_defecto: tuple[str, ...]) -> Path:
    """Devuelve el directorio base XDG; ignora valores vacíos o relativos."""
    valor = os.environ.get(variable, "")
    if valor and Path(valor).is_absolute():
        return Path(valor)
    return Path.home().joinpath(*por_defecto)


def directorio_datos() -> Path:
    return _directorio_xdg("XDG_DATA_HOME", (".local", "share")) / _NOMBRE


def directorio_cache() -> Path:
    return _directorio_xdg("XDG_CACHE_HOME", (".cache",)) / _NOMBRE


def directorio_config() -> Path:
    return _directorio_xdg("XDG_CONFIG_HOME", (".config",)) / _NOMBRE


def ruta_base_de_datos() -> Path:
    return directorio_datos() / "vozflow.db"


def directorio_pruebas() -> Path:
    """Audios de las mediciones; quedan fuera del repositorio."""
    return directorio_datos() / "pruebas"


def ruta_token_portal() -> Path:
    """Token de restauración del portal de escritorio remoto."""
    return directorio_config() / "portal-token"


def asegurar(directorio: Path) -> Path:
    """Crea el directorio si falta, accesible solo para el usuario."""
    directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
    directorio.chmod(0o700)
    return directorio
