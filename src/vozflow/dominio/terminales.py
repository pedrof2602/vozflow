"""Qué aplicaciones son terminales (decide el modo de pegado y el modo «Terminal»)."""

from collections.abc import Collection

_TERMINALES = frozenset(
    {
        "ptyxis",
        "konsole",
        "gnome-terminal",
        "gnome-terminal-server",
        "kitty",
        "alacritty",
        "wezterm",
        "foot",
        "tilix",
        "xterm",
        "terminator",
        "ghostty",
        "kgx",
        "org.gnome.console",
    }
)


def _normalizar(aplicacion: str) -> str:
    return aplicacion.strip().lower()


def es_terminal(aplicacion: str, marcadas: Collection[str] = ()) -> bool:
    """``marcadas``: aplicaciones que la persona marcó a mano como terminal."""
    nombre = _normalizar(aplicacion)
    if not nombre:
        return False
    if nombre in {_normalizar(m) for m in marcadas}:
        return True
    if nombre in _TERMINALES:
        return True
    # Identificadores tipo «org.gnome.Ptyxis»: vale el último componente.
    return "." in nombre and nombre.rsplit(".", 1)[-1] in _TERMINALES
