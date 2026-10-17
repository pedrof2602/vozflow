"""Plataforma gráfica y arranque con la sesión: lo de la interfaz que no necesita cargar Qt."""

import os
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path

_MARCA = "X-Vozflow-Generado=true"


def elegir_plataforma(entorno: Mapping[str, str]) -> str:
    """``xcb`` (XWayland) si está: es la única forma de que el indicador flote arriba y sin foco.

    Si la persona ya fijó ``QT_QPA_PLATFORM``, se respeta; sin XWayland se vuelve a ``wayland``.
    """
    if entorno.get("QT_QPA_PLATFORM"):
        return entorno["QT_QPA_PLATFORM"]
    return "xcb" if entorno.get("DISPLAY") else "wayland"


def fijar_plataforma(entorno: MutableMapping[str, str] | None = None) -> str:
    """Hay que llamarla **antes** de crear la ``QApplication``."""
    destino: MutableMapping[str, str] = os.environ if entorno is None else entorno
    plataforma = elegir_plataforma(destino)
    destino["QT_QPA_PLATFORM"] = plataforma
    return plataforma


# ---- inicio automático con la sesión ----------------------------------------------------


def _archivo(config: Path) -> Path:
    return config / "autostart" / "vozflow.desktop"


def autoinicio_activo(config: Path) -> bool:
    archivo = _archivo(config)
    return archivo.is_file() and _MARCA in archivo.read_text(encoding="utf-8")


def activar_autoinicio(config: Path, comando: str | Sequence[str]) -> Path:
    """Escribe ``~/.config/autostart/vozflow.desktop``. No pisa un archivo ajeno."""
    archivo = _archivo(config)
    if archivo.exists() and _MARCA not in archivo.read_text(encoding="utf-8"):
        raise FileExistsError(f"{archivo} existe y no lo generó vozflow")
    palabras = [comando] if isinstance(comando, str) else list(comando)
    exec_ = " ".join(f'"{p}"' if " " in p else p for p in palabras)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=vozflow",
                "Comment=Dictado por voz local",
                f"Exec={exec_}",
                "Terminal=false",
                "X-GNOME-Autostart-enabled=true",
                _MARCA,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return archivo


def desactivar_autoinicio(config: Path) -> bool:
    """Borra el archivo solo si lo generó vozflow. Devuelve si lo borró."""
    archivo = _archivo(config)
    if not autoinicio_activo(config):
        return False
    archivo.unlink()
    return True
