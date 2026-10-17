"""Respaldo: atajos de teclado con ``ydotool key`` (necesita ``ydotoold`` y ``/dev/uinput``).

Solo manda atajos conocidos, nunca ``ydotool type``: ese comando supone un teclado de EE. UU. y
con el ``latam`` de Pedro escribiría mal la ñ y los acentos.
"""

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from vozflow.insercion.puerto import FalloDeTeclado

# keysym → código de tecla de Linux (input-event-codes.h)
_CODIGOS = {
    0xFFE1: 42,  # Shift izquierdo
    0xFFE3: 29,  # Control izquierdo
    0xFF63: 110,  # Insert
    0x76: 47,  # v
}
_TOPE_S = 3.0

Ejecutor = Callable[[list[str], dict[str, str], float], "subprocess.CompletedProcess[str]"]


def socket_de_ydotool() -> Path:
    explicito = os.environ.get("YDOTOOL_SOCKET")
    if explicito:
        return Path(explicito)
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / ".ydotool_socket"


def _ejecutar(
    comando: list[str], entorno: dict[str, str], timeout_s: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        comando,
        env={**os.environ, **entorno},
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


class TecladorYdotool:
    def __init__(self, socket: Path | None = None, ejecutar: Ejecutor = _ejecutar) -> None:
        self._socket = socket or socket_de_ydotool()
        self._ejecutar = ejecutar

    def pulsar_combinacion(self, teclas: Sequence[int]) -> None:
        if not teclas:
            return
        try:
            codigos = [_CODIGOS[t] for t in teclas]
        except KeyError as error:
            raise FalloDeTeclado(
                "ydotool solo sabe mandar los atajos de pegado conocidos"
            ) from error
        if not self._socket.exists():
            raise FalloDeTeclado(
                f"No está corriendo ydotoold (falta {self._socket}); "
                "arrancalo con systemctl para usar ydotool"
            )
        secuencia = [f"{c}:1" for c in codigos] + [f"{c}:0" for c in reversed(codigos)]
        try:
            resultado = self._ejecutar(
                ["ydotool", "key", *secuencia], {"YDOTOOL_SOCKET": str(self._socket)}, _TOPE_S
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FalloDeTeclado(f"ydotool no respondió: {type(error).__name__}") from error
        if resultado.returncode != 0:
            raise FalloDeTeclado(f"ydotool falló (código {resultado.returncode})")
