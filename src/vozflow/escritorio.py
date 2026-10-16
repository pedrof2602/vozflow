"""Entrada de escritorio de vozflow (``vozflow.desktop``).

El portal de GNOME identifica a una aplicación que no está empaquetada por su entrada de
escritorio: sin ella, ``Registry.Register`` falla con «App info not found» y no se pueden usar
los atajos globales. La misma entrada sirve después para el menú y el inicio automático.
"""

import logging
import shutil
from pathlib import Path

from vozflow import rutas

ID_DE_APLICACION = "vozflow"
_MARCA = "X-Vozflow-Generado=true"
_registro = logging.getLogger(__name__)


def ruta_de_la_entrada() -> Path:
    return rutas.directorio_de_aplicaciones() / f"{ID_DE_APLICACION}.desktop"


def _para_exec(texto: str) -> str:
    """Las rutas con espacios van entre comillas, según la especificación de ``Exec``."""
    return f'"{texto}"' if " " in texto else texto


def _contenido(ruta_uv: str, proyecto: Path) -> str:
    orden = f"{_para_exec(ruta_uv)} run --project {_para_exec(str(proyecto))} python -m vozflow"
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=vozflow",
            "Comment=Dictado por voz local",
            f"Exec={orden}",
            "Terminal=false",
            "NoDisplay=true",
            "Categories=Utility;",
            _MARCA,
            "",
        ]
    )


def asegurar_entrada_de_escritorio(
    *, ruta_uv: str | None = None, proyecto: Path | None = None
) -> Path:
    """Crea o actualiza ``vozflow.desktop``. No toca un archivo que no haya generado vozflow."""
    ruta_uv = ruta_uv or shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    proyecto = proyecto or Path(__file__).resolve().parents[2]
    destino = ruta_de_la_entrada()
    nuevo = _contenido(ruta_uv, proyecto)
    if destino.exists():
        actual = destino.read_text(encoding="utf-8")
        if actual == nuevo:
            return destino
        if _MARCA not in actual:
            _registro.warning("%s existe pero no lo generó vozflow; no se modifica", destino)
            return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(nuevo, encoding="utf-8")
    destino.chmod(0o644)
    return destino


def retirar_entrada_de_escritorio() -> bool:
    """Borra la entrada solo si la generó vozflow. Devuelve si la borró."""
    destino = ruta_de_la_entrada()
    if not destino.is_file() or _MARCA not in destino.read_text(encoding="utf-8"):
        return False
    destino.unlink()
    return True
